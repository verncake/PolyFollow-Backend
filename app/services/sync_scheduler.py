"""
Periodic Sync Scheduler.

Background task that periodically syncs trades and positions for tracked addresses.
Uses the sync_state table to track which addresses need syncing and runs
incremental updates every 5 minutes for addresses with stale data.
"""
import asyncio
import logging
from datetime import datetime

from app.core.database import get_db_service
from app.core.redis import acquire_sync_lock, release_sync_lock
from app.services.pnl_service import get_pnl_service

logger = logging.getLogger(__name__)

# Sync interval in seconds
SYNC_INTERVAL_SECONDS = 300  # 5 minutes

# Stale threshold in minutes
STALE_THRESHOLD_MINUTES = 5


class SyncScheduler:
    """Periodic sync scheduler that runs incremental updates for tracked addresses."""

    def __init__(self):
        self.db = get_db_service()
        self.pnl_service = get_pnl_service()
        self._running = False
        self._task = None

    async def sync_stale_addresses(self) -> dict:
        """
        Sync all addresses with stale data.

        Returns:
            dict with sync results for each address
        """
        # Get addresses that need syncing (stale > 5 minutes)
        stale_addresses = await self.db.get_stale_sync_addresses(STALE_THRESHOLD_MINUTES)

        if not stale_addresses:
            logger.debug("No stale addresses to sync")
            return {"synced": [], "skipped": 0, "errors": []}

        logger.info(f"Found {len(stale_addresses)} addresses with stale data to sync")

        results = {
            "synced": [],
            "skipped": 0,
            "errors": [],
        }

        for address in stale_addresses:
            # Try to acquire distributed lock for this address
            sync_lock = acquire_sync_lock(address)
            if sync_lock is None:
                logger.debug(f"Skipping {address}: lock held by another process")
                results["skipped"] += 1
                continue

            try:
                # Sync trades for this address
                trades_result = await self.pnl_service.sync_trades_for_address(
                    user_address=address,
                    force_refresh=False,  # Incremental sync
                )

                # Sync positions for this address
                positions_result = await self.pnl_service.sync_positions_for_address(
                    user_address=address,
                    force_refresh=False,
                )

                # Sync activities for this address (includes REDEEM for pending_redeem proxy timestamps)
                activity_result = await self.pnl_service.sync_activity_for_address(
                    user_address=address,
                    force_refresh=False,
                )

                results["synced"].append(address)
                logger.info(
                    f"Synced {address}: "
                    f"{trades_result.get('new_trades', 0)} new trades, "
                    f"{positions_result.get('positions_upserted', 0)} positions, "
                    f"{activity_result.get('activities_upserted', 0)} activities"
                )

                # Rate limit to avoid overwhelming the API
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error syncing {address}: {e}")
                results["errors"].append({"address": address, "error": str(e)})
            finally:
                # Always release the lock
                sync_lock.release()

        return results

    async def run_periodic_sync(self):
        """Run periodic sync loop."""
        logger.info(
            f"Sync scheduler started. Running every {SYNC_INTERVAL_SECONDS} seconds "
            f"for addresses with stale data (>{STALE_THRESHOLD_MINUTES} min)"
        )

        self._running = True

        while self._running:
            try:
                # Check if there are addresses that need syncing
                stale_addresses = await self.db.get_stale_sync_addresses(STALE_THRESHOLD_MINUTES)

                if stale_addresses:
                    logger.info(f"Periodic sync: found {len(stale_addresses)} stale addresses")
                    await self.sync_stale_addresses()
                else:
                    logger.debug("Periodic sync: no stale addresses")

            except Exception as e:
                logger.error(f"Error in periodic sync loop: {e}")

            # Wait for next interval
            await asyncio.sleep(SYNC_INTERVAL_SECONDS)

    def start(self):
        """Start the background sync task."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run_periodic_sync())
            logger.info("Sync scheduler background task started")

    async def stop(self):
        """Stop the background sync task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("Sync scheduler background task stopped")

    async def trigger_sync(self, address: str) -> dict:
        """
        Manually trigger sync for a specific address.

        Returns:
            dict with sync results
        """
        # Try to acquire distributed lock for this address
        sync_lock = acquire_sync_lock(address)
        if sync_lock is None:
            return {
                "status": "skipped",
                "address": address,
                "reason": "lock_held_by_another_process",
            }

        try:
            trades_result = await self.pnl_service.sync_trades_for_address(
                user_address=address,
                force_refresh=False,
            )
            positions_result = await self.pnl_service.sync_positions_for_address(
                user_address=address,
                force_refresh=False,
            )
            activity_result = await self.pnl_service.sync_activity_for_address(
                user_address=address,
                force_refresh=False,
            )
            return {
                "status": "completed",
                "address": address,
                "trades": trades_result,
                "positions": positions_result,
                "activities": activity_result,
            }
        except Exception as e:
            logger.error(f"Error triggering sync for {address}: {e}")
            return {
                "status": "error",
                "address": address,
                "error": str(e),
            }
        finally:
            # Always release the lock
            sync_lock.release()


# Singleton instance
_scheduler: SyncScheduler = None


def get_sync_scheduler() -> SyncScheduler:
    """Get the sync scheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = SyncScheduler()
    return _scheduler
