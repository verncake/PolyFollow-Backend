"""
Scoring service for calculating trader performance scores (10 dimensions).

10维度评分系统:
1. Profitability (盈利能力) - Realized + Unrealized PnL
2. Win Rate (胜率) - 赢的仓位占比
3. Profit Factor (盈亏比) - 盈利/亏损比
4. Risk Mgmt (风险管理) - 仓位比例 + 止损行为
5. Experience (交易经验) - 交易时长 + 次数
6. Pos. Control (仓位控制) - 最大仓位占比
7. Anti-Bot (反机器人) - 行为模式检测
8. Focus (专注度) - 领域集中度
9. Close Disc. (平仓纪律) - 主动平仓比例
10. Capital (资金体量) - 总资金

每个维度 0-10 分，最终加权求和到 0-100 分。
"""
import math
import statistics
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field


# 10维度权重配置
DEFAULT_WEIGHTS = {
    "profitability": 0.15,
    "win_rate": 0.15,
    "profit_factor": 0.15,
    "risk_mgmt": 0.10,
    "experience": 0.10,
    "pos_control": 0.10,
    "anti_bot": 0.05,
    "focus": 0.05,
    "close_disc": 0.10,
    "capital": 0.05,
}


@dataclass
class AddressScores:
    """10维度评分结果."""
    address: str

    # 原始值
    profitability_raw: float = 0.0       # 绝对P/L
    win_rate_raw: float = 0.0           # 0-100%
    profit_factor_raw: float = 0.0      # 盈亏比
    risk_mgmt_raw: float = 0.0          # 风险管理指标
    experience_raw: float = 0.0         # 经验值
    pos_control_raw: float = 0.0        # 仓位控制
    anti_bot_raw: float = 0.0           # 反Bot分数
    focus_raw: float = 0.0              # 专注度
    close_disc_raw: float = 0.0         # 平仓纪律
    capital_raw: float = 0.0            # 资金体量

    # 标准化分数 (0-10)
    profitability: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    risk_mgmt: float = 0.0
    experience: float = 0.0
    pos_control: float = 0.0
    anti_bot: float = 0.0
    focus: float = 0.0
    close_disc: float = 0.0
    capital: float = 0.0

    # 综合分 (0-100)
    total_score: int = 0

    # 元数据
    data_quality: str = "full"  # "full", "partial", "insufficient"

    # Bot风险检测
    risk_flags: List[str] = field(default_factory=list)  # 风险标志列表
    micro_win_count: int = 0  # 蚂蚁仓位数 ($0.1-$1)
    micro_win_ratio: float = 0.0  # 蚂蚁仓位占比

    def to_dict(self) -> Dict[str, Any]:
        return {
            "address": self.address,
            "total_score": self.total_score,
            "data_quality": self.data_quality,
            "risk_flags": self.risk_flags,
            "risk_level": "HIGH" if self.risk_flags else "NORMAL",
            "micro_win_count": self.micro_win_count,
            "micro_win_ratio": round(self.micro_win_ratio, 2),
            "dimensions": {
                "profitability": {"score": round(self.profitability, 2), "raw": round(self.profitability_raw, 4)},
                "win_rate": {"score": round(self.win_rate, 2), "raw": round(self.win_rate_raw, 2)},
                "profit_factor": {"score": round(self.profit_factor, 2), "raw": round(self.profit_factor_raw, 2)},
                "risk_mgmt": {"score": round(self.risk_mgmt, 2), "raw": round(self.risk_mgmt_raw, 2)},
                "experience": {"score": round(self.experience, 2), "raw": round(self.experience_raw, 2)},
                "pos_control": {"score": round(self.pos_control, 2), "raw": round(self.pos_control_raw, 2)},
                "anti_bot": {"score": round(self.anti_bot, 2), "raw": round(self.anti_bot_raw, 2)},
                "focus": {"score": round(self.focus, 2), "raw": round(self.focus_raw, 4)},
                "close_disc": {"score": round(self.close_disc, 2), "raw": round(self.close_disc_raw, 2)},
                "capital": {"score": round(self.capital, 2), "raw": round(self.capital_raw, 2)},
            }
        }


class AddressScorer:
    """
    10维度地址评分器.

    输入: positions, closed_positions, trades
    输出: AddressScores (各维度0-10分, 总分0-100)
    """

    # 过滤掉总交易额小于此值的仓位 (防刷胜率)
    # 设置为 $0.1 以识别蚂蚁仓位和Bot刷尾盘行为
    MIN_TRADE_VALUE = 0.1

    # 评分映射常量
    PF_MAX_SCALE = 5.0       # Profit Factor 映射: 5.0 = 满分
    CAPITAL_P99 = 10000.0    # 资金量 P99 基准
    MAX_EXPOSURE_DANGER = 0.80  # 超过80%单一仓位为危险

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or DEFAULT_WEIGHTS.copy()

    def score_address(
        self,
        address: str,
        positions: List[Dict[str, Any]],
        closed_positions: List[Dict[str, Any]],
        trades: List[Dict[str, Any]],
        account_age_days: Optional[int] = None,
        total_capital: Optional[float] = None,
    ) -> AddressScores:
        """
        计算地址的综合评分.

        Args:
            address: 钱包地址
            positions: 当前持仓
            closed_positions: 已平仓仓位
            trades: 交易历史
            account_age_days: 账户年龄(天数), None则从trades推断
            total_capital: 总资金, None则从positions计算

        Returns:
            AddressScores 对象
        """
        scores = AddressScores(address=address)

        # 计算10个维度的原始值
        (
            scores.profitability_raw,
            scores.win_rate_raw,
            scores.profit_factor_raw,
            scores.risk_mgmt_raw,
            scores.experience_raw,
            scores.pos_control_raw,
            scores.anti_bot_raw,
            scores.focus_raw,
            scores.close_disc_raw,
            scores.capital_raw,
            scores.micro_win_count,
            scores.micro_win_ratio,
        ) = self._calculate_raw_dimensions(
            address, positions, closed_positions, trades,
            account_age_days, total_capital
        )

        # 检测数据质量
        total_closed = len(closed_positions)
        total_trades = len(trades)
        if total_closed < 3 or total_trades < 5:
            scores.data_quality = "insufficient"
        elif total_closed < 10 or total_trades < 20:
            scores.data_quality = "partial"

        # 映射到 0-10 分
        scores.profitability = self._map_profitability(scores.profitability_raw)
        scores.win_rate = self._map_win_rate(scores.win_rate_raw)
        scores.profit_factor = self._map_profit_factor(scores.profit_factor_raw)
        scores.risk_mgmt = self._map_risk_mgmt(scores.risk_mgmt_raw)
        scores.experience = self._map_experience(scores.experience_raw)
        scores.pos_control = self._map_pos_control(scores.pos_control_raw)
        scores.anti_bot = self._map_anti_bot(scores.anti_bot_raw)
        scores.focus = self._map_focus(scores.focus_raw)
        scores.close_disc = self._map_close_disc(scores.close_disc_raw)
        scores.capital = self._map_capital(scores.capital_raw)

        # 计算加权总分 (0-100)
        scores.total_score = int(round(
            scores.profitability * self.weights["profitability"] +
            scores.win_rate * self.weights["win_rate"] +
            scores.profit_factor * self.weights["profit_factor"] +
            scores.risk_mgmt * self.weights["risk_mgmt"] +
            scores.experience * self.weights["experience"] +
            scores.pos_control * self.weights["pos_control"] +
            scores.anti_bot * self.weights["anti_bot"] +
            scores.focus * self.weights["focus"] +
            scores.close_disc * self.weights["close_disc"] +
            scores.capital * self.weights["capital"]
        ) * 10)

        # Bot风险检测
        scores.risk_flags = self._detect_risk_flags(
            closed_positions, trades, scores.anti_bot_raw, scores.micro_win_ratio
        )

        # 如果有Bot风险标志，降低综合评分
        if "BOT_SCRAPER" in scores.risk_flags or "BOT_SIGNAL" in scores.risk_flags:
            scores.total_score = int(scores.total_score * 0.5)  # 高频Bot评分打5折

        return scores

    def _calculate_raw_dimensions(
        self,
        address: str,
        positions: List[Dict[str, Any]],
        closed_positions: List[Dict[str, Any]],
        trades: List[Dict[str, Any]],
        account_age_days: Optional[int],
        total_capital: Optional[float],
    ) -> Tuple[float, float, float, float, float, float, float, float, float, float, int, float]:
        """计算10个维度的原始值."""

        # === 1. Profitability ===
        realized_pnl = sum(p.get("realizedPnl", 0) for p in closed_positions)
        unrealized_pnl = sum(p.get("cashPnl", 0) for p in positions)
        profitability = realized_pnl + unrealized_pnl

        # === 2. Win Rate (过滤小额仓位) ===
        valid_closed = [p for p in closed_positions
                       if abs(p.get("avgPrice", 0) * p.get("totalBought", 0)) >= self.MIN_TRADE_VALUE]
        winning_closed = [p for p in valid_closed if p.get("realizedPnl", 0) > 0]
        win_rate = len(winning_closed) / len(valid_closed) * 100 if valid_closed else 0.0

        # === 3. Profit Factor ===
        gross_profit = sum(p.get("realizedPnl", 0) for p in valid_closed if p.get("realizedPnl", 0) > 0)
        gross_loss = abs(sum(p.get("realizedPnl", 0) for p in valid_closed if p.get("realizedPnl", 0) < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        # === 4. Risk Mgmt ===
        avg_winning_size = statistics.mean([
            p.get("avgPrice", 0) * p.get("totalBought", 0)
            for p in valid_closed if p.get("realizedPnl", 0) > 0
        ]) if winning_closed else 0.0
        avg_losing_size = statistics.mean([
            abs(p.get("avgPrice", 0) * p.get("totalBought", 0))
            for p in valid_closed if p.get("realizedPnl", 0) < 0
        ]) if any(p.get("realizedPnl", 0) < 0 for p in valid_closed) else 0.0
        risk_mgmt_ratio = avg_winning_size / avg_losing_size if avg_losing_size > 0 else (2.0 if avg_winning_size > 0 else 0.0)

        # === 5. Experience ===
        if account_age_days is None and trades:
            timestamps = [t.get("timestamp", 0) for t in trades if t.get("timestamp", 0) > 0]
            if timestamps:
                account_age_days = (max(timestamps) - min(timestamps)) / 86400 if len(timestamps) > 1 else 1
            else:
                account_age_days = 1
        account_age_days = max(1, account_age_days or 1)
        experience_trades = len(trades)

        # 组合经验值: sqrt(天数 * 交易数) 作为原始值
        experience_raw = math.sqrt(account_age_days * experience_trades)

        # === 6. Pos. Control (最大仓位占比) ===
        if total_capital is None:
            total_capital = sum(p.get("currentValue", 0) for p in positions) + 100  # 假设最低100
        max_position_value = max(
            [abs(p.get("currentValue", 0)) for p in positions] +
            [abs(p.get("avgPrice", 0) * p.get("totalBought", 0)) for p in closed_positions]
        ) if (positions or closed_positions) else 0.0
        pos_control_raw = max_position_value / total_capital if total_capital > 0 else 0.0

        # === 7. Anti-Bot ===
        anti_bot_raw = self._calculate_anti_bot_score(trades)

        # === 8. Focus (HHI 集中度) ===
        focus_raw = self._calculate_focus_score(positions, closed_positions)

        # === 9. Close Disc. (主动平仓 vs 系统赎回) ===
        close_disc_raw = self._calculate_close_disc_score(trades)

        # === 10. Capital ===
        capital_raw = total_capital or 0.0

        # === Micro-win detection (Bot刷尾盘特征) ===
        micro_win_count = 0
        for p in closed_positions:
            pnl = p.get("realizedPnl", 0)
            if 0 < pnl < 1.0:  # 蚂蚁仓位: 盈利$0.1-$1
                micro_win_count += 1
        micro_win_ratio = micro_win_count / len(closed_positions) if closed_positions else 0.0

        return (
            profitability, win_rate, profit_factor, risk_mgmt_ratio,
            experience_raw, pos_control_raw, anti_bot_raw, focus_raw,
            close_disc_raw, capital_raw, micro_win_count, micro_win_ratio
        )

    def _calculate_anti_bot_score(self, trades: List[Dict[str, Any]]) -> float:
        """
        Anti-Bot 检测:
        A. 睡眠规律: 24小时分布方差
        B. 整数金额偏好: 精确$10, $50等
        """
        if len(trades) < 10:
            return 5.0  # 数据不足给5分

        # A. 睡眠规律检测
        from datetime import datetime, timezone
        hour_distribution = [0] * 24
        for t in trades:
            ts = t.get("timestamp", 0)
            if ts > 0:
                hour = datetime.fromtimestamp(ts, tz=timezone.utc).hour
                hour_distribution[hour] += 1

        # 计算方差
        mean_trades = sum(hour_distribution) / 24
        variance = sum((h - mean_trades) ** 2 for h in hour_distribution) / 24

        # 找到最大连续低谷(睡眠时间)
        max_sleep_hours = 0
        current_sleep = 0
        for count in hour_distribution:
            if count < mean_trades * 0.3:  # 低于均值30%认为睡眠
                current_sleep += 1
                max_sleep_hours = max(max_sleep_hours, current_sleep)
            else:
                current_sleep = 0

        # 人类应该有6+小时睡眠低谷
        sleep_score = min(max_sleep_hours / 6.0, 1.0) if max_sleep_hours >= 6 else max_sleep_hours / 6.0

        # B. 整数金额偏好
        integer_preferences = 0
        total_value_trades = 0
        for t in trades:
            size = t.get("size", 0)
            price = t.get("price", 0)
            if size > 0 and price > 0:
                total_value = size * price
                total_value_trades += 1
                # 检查是否整数或整0.5
                if abs(total_value - round(total_value)) < 0.01 or \
                   abs(total_value - round(total_value * 2) / 2) < 0.01:
                    integer_preferences += 1

        integer_ratio = integer_preferences / total_value_trades if total_value_trades > 0 else 0
        # 整数偏好超过90%疑似Bot
        bot_score = 1.0 if integer_ratio > 0.9 else integer_ratio / 0.9

        # 综合: 方差小(24小时均匀分布) + 整数偏好高 = Bot
        # 返回"像人类"的程度 (1.0 = 完全像人, 0.0 = 完全像Bot)
        human_score = (sleep_score + bot_score) / 2
        return human_score * 10  # 映射到 0-10

    def _calculate_focus_score(
        self,
        positions: List[Dict[str, Any]],
        closed_positions: List[Dict[str, Any]]
    ) -> float:
        """
        Focus 专注度: 使用 HHI 计算领域集中度.
        HHI = sum(category_share^2), 越低越分散, 越高越专注.
        Focus Score = 1 - HHI (标准化)
        """
        all_positions = positions + closed_positions

        # 统计各 categories 数量
        categories = {}
        for p in all_positions:
            cat = p.get("eventSlug", "unknown")
            if cat:
                categories[cat] = categories.get(cat, 0) + 1

        if not categories:
            return 5.0  # 默认中等

        total = sum(categories.values())
        hhi = sum((count / total) ** 2 for count in categories.values())

        # HHI: 1 = 完全专注, ~0 = 完全分散
        # Focus Score: 1 - HHI (越分散越专注? 不, 专注度应该衡量是否领域专家)
        # 重新定义: 专注度 = 1 - |HHI - expected_HHI|
        # 假设完全分散时 HHI -> 0, 专注时 HHI -> 1
        # 专注的人应该在某个领域有突出优势
        # 简单实现: Focus Score = HHI * 10 (专注的人分数高)
        return min(hhi * 10, 10.0)

    def _calculate_close_disc_score(self, trades: List[Dict[str, Any]]) -> float:
        """
        Close Disc. 平仓纪律:
        统计盈利仓位中, 主动 SELL vs 系统 REDEEM 的比例.
        主动在高位卖出 = 好纪律.
        """
        # 注意: Polymarket API 不直接区分 SELL 还是 REDEEM
        # 我们通过交易方向和价格推断:
        # - 如果以 SELL 结束且价格 > 0.90, 认为主动平仓
        # - 如果以 BUY 结束, 认为是尝试抄底(不算主动平仓)

        sell_ended_profitable = 0
        total_profitable_closed = 0

        # 按 asset 分组看最后一笔交易
        asset_last_trade = {}
        for t in sorted(trades, key=lambda x: x.get("timestamp", 0)):
            asset = t.get("asset")
            if asset:
                asset_last_trade[asset] = t

        for asset, last_trade in asset_last_trade.items():
            side = last_trade.get("side", "").upper()
            price = last_trade.get("price", 0)

            # 盈利仓位判断: 价格为1.0 (完结) 或最后价格 > 0.9
            if price >= 0.90:
                total_profitable_closed += 1
                if side == "SELL" and price >= 0.90:
                    sell_ended_profitable += 1

        if total_profitable_closed == 0:
            return 5.0  # 数据不足

        return (sell_ended_profitable / total_profitable_closed) * 10

    def _detect_risk_flags(
        self,
        closed_positions: List[Dict[str, Any]],
        trades: List[Dict[str, Any]],
        anti_bot_score: float,
        micro_win_ratio: float,
    ) -> List[str]:
        """
        检测风险标志.

        风险类型:
        - BOT_SCRAPER: 高频刷尾盘 (micro_win_ratio > 50%)
        - BOT_SIGNAL: Bot行为特征 (anti_bot_score < 3)
        - LOW_EXPERIENCE: 经验不足 (< 10次交易)
        """
        risk_flags = []

        # Bot刷尾盘检测: 超过50%的盈利仓位是蚂蚁仓位
        if micro_win_ratio > 0.5:
            risk_flags.append("BOT_SCRAPER")

        # Bot行为检测: anti_bot分数极低
        if anti_bot_score < 3.0:
            risk_flags.append("BOT_SIGNAL")

        # 经验不足
        if len(trades) < 10:
            risk_flags.append("LOW_EXPERIENCE")

        return risk_flags

    # ========== 评分映射函数 (原始值 -> 0-10) ==========

    def _map_profitability(self, raw: float) -> float:
        """
        Profitability: 对数归一化避免首富压缩其他人.
        log(1 + abs(x)) / log(1 + max_expected) * 10
        """
        if raw <= 0:
            return max(0.0, 5.0 + raw / 10)  # 亏损也给出路
        # 对数归一化
        log_pnl = math.log1p(raw)
        max_log = math.log1p(10000)  # 假设1万是好成绩
        return min(log_pnl / max_log * 10, 10.0)

    def _map_win_rate(self, raw: float) -> float:
        """Win Rate: 0-100% 直接映射到 0-10"""
        return min(raw / 100 * 10, 10.0)

    def _map_profit_factor(self, raw: float) -> float:
        """Profit Factor: 0-5+ 映射到 0-10"""
        return min(raw / self.PF_MAX_SCALE * 10, 10.0)

    def _map_risk_mgmt(self, raw: float) -> float:
        """Risk Mgmt: avg_winning / avg_losing, >1.5 好, <1 差"""
        # 1.0 = 平, 2.0 = 好, 3.0+ = 优秀
        return min(raw / 2.0 * 10, 10.0)

    def _map_experience(self, raw: float) -> float:
        """Experience: sqrt(days * trades) 对数增长"""
        # sqrt(30 * 100) = 55 -> 约7分
        # sqrt(365 * 1000) = 604 -> 满分
        return min(math.log1p(raw) / math.log1p(600) * 10, 10.0)

    def _map_pos_control(self, raw: float) -> float:
        """Pos Control: 单一仓位占比, <20% 好, >80% 危险"""
        # 占比越低越好
        if raw <= 0.15:
            return 10.0
        elif raw <= 0.20:
            return 8.0
        elif raw <= 0.30:
            return 6.0
        elif raw <= 0.50:
            return 4.0
        elif raw <= 0.80:
            return 2.0
        else:
            return 0.0

    def _map_anti_bot(self, raw: float) -> float:
        """Anti-Bot: 直接使用计算出的像人程度"""
        return min(raw, 10.0)

    def _map_focus(self, raw: float) -> float:
        """Focus: HHI * 10, 专注者高分"""
        return min(raw, 10.0)

    def _map_close_disc(self, raw: float) -> float:
        """Close Disc: 主动平仓比例"""
        return min(raw, 10.0)

    def _map_capital(self, raw: float) -> float:
        """Capital: 分位数思想, 1万=8分, 10万=10分"""
        if raw <= 0:
            return 0.0
        # log scale: 100 -> ~5分, 1000 -> ~7分, 10000 -> 9分
        return min(math.log10(raw + 1) / 4 * 10, 10.0)


# ========== 兼容旧接口 ==========

def get_scoring_service() -> AddressScorer:
    """Get the singleton scoring service instance."""
    global _address_scorer
    if _address_scorer is None:
        _address_scorer = AddressScorer()
    return _address_scorer


_address_scorer: Optional[AddressScorer] = None


# 保留旧接口用于兼容
class ScoringService:
    """Legacy scoring service for backward compatibility."""

    def __init__(self):
        self._scorer = AddressScorer()

    def score_from_positions_and_trades(
        self,
        address: str,
        positions: List[Dict[str, Any]],
        closed_positions: List[Dict[str, Any]],
        trades: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Legacy interface."""
        scores = self._scorer.score_address(
            address, positions, closed_positions, trades
        )
        return scores.to_dict()


def get_address_scores(
    address: str,
    positions: List[Dict[str, Any]],
    closed_positions: List[Dict[str, Any]],
    trades: List[Dict[str, Any]],
    **kwargs
) -> AddressScores:
    """Convenience function for scoring an address."""
    return get_scoring_service().score_address(
        address, positions, closed_positions, trades, **kwargs
    )
