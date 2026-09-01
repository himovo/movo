from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/mock/sales-review", tags=["mock-sales-review"])


class ApiResponse(BaseModel):
    code: int = 0
    message: Optional[str] = None
    data: Optional[object] = None


def _period_label(period: str) -> str:
    if period == "current":
        return "2026-05"
    return period or "2026-05"


def _sales_target(period: str) -> dict[str, Any]:
    period = _period_label(period)
    return {
        "period": period,
        "metric": "new_contract_amount",
        "metric_name": "新增合同额",
        "currency": "CNY",
        "target_amount": 12_000_000,
        "actual_amount": 8_150_000,
        "completion_rate": 0.6792,
        "elapsed_rate": 0.8065,
        "gap_amount": 3_850_000,
        "pace_status": "behind",
        "scope": "华东直营销售团队",
        "review_cutoff": f"{period}-25",
        "business_calendar": {
            "period_days": 31,
            "elapsed_days": 25,
            "remaining_days": 6,
            "working_days_remaining": 5,
        },
        "policy_reference": {
            "name": "销售经营复盘口径",
            "source": "mock knowledge base",
            "effective_date": "2026-01-01",
            "notes": "新增合同额按已签署合同归属月统计，续约不计入新增合同额。",
        },
    }


def _sales_funnel(period: str) -> dict[str, Any]:
    period = _period_label(period)
    return {
        "period": period,
        "stages": [
            {
                "stage": "leads",
                "stage_name": "线索",
                "count": 1840,
                "target_count": 2100,
                "historical_avg_count": 1980,
                "conversion_to_next": 0.226,
                "historical_avg_conversion": 0.238,
                "status": "slightly_below",
            },
            {
                "stage": "qualified_opportunities",
                "stage_name": "有效商机",
                "count": 416,
                "target_count": 500,
                "historical_avg_count": 471,
                "conversion_to_next": 0.382,
                "historical_avg_conversion": 0.415,
                "status": "below",
            },
            {
                "stage": "proposal",
                "stage_name": "报价/方案",
                "count": 159,
                "target_count": 210,
                "historical_avg_count": 195,
                "conversion_to_next": 0.358,
                "historical_avg_conversion": 0.402,
                "status": "below",
            },
            {
                "stage": "contracted",
                "stage_name": "签约",
                "count": 57,
                "target_count": 86,
                "historical_avg_count": 78,
                "conversion_to_next": None,
                "historical_avg_conversion": None,
                "status": "below",
            },
        ],
        "diagnostic_hints": [
            "有效商机到报价阶段转化低于历史均值，可能存在中段推进瓶颈。",
            "报价到签约转化低于历史均值，大额项目延期会放大目标缺口。",
        ],
    }


def _sales_regions(period: str) -> list[dict[str, Any]]:
    period = _period_label(period)
    return [
        {
            "period": period,
            "region_id": "east-shanghai",
            "region_name": "上海",
            "manager": "周敏",
            "target_amount": 4_500_000,
            "actual_amount": 3_820_000,
            "completion_rate": 0.8489,
            "pipeline_amount": 2_100_000,
            "win_rate": 0.312,
            "risk_level": "medium",
            "main_issue": "两个重点项目审批周期延长",
        },
        {
            "period": period,
            "region_id": "east-jiangsu",
            "region_name": "江苏",
            "manager": "沈佳",
            "target_amount": 3_800_000,
            "actual_amount": 1_960_000,
            "completion_rate": 0.5158,
            "pipeline_amount": 1_480_000,
            "win_rate": 0.241,
            "risk_level": "high",
            "main_issue": "新线索不足，有效商机规模偏低",
        },
        {
            "period": period,
            "region_id": "east-zhejiang",
            "region_name": "浙江",
            "manager": "陈远",
            "target_amount": 2_600_000,
            "actual_amount": 1_730_000,
            "completion_rate": 0.6654,
            "pipeline_amount": 1_250_000,
            "win_rate": 0.287,
            "risk_level": "medium",
            "main_issue": "报价后成交周期拉长",
        },
        {
            "period": period,
            "region_id": "east-anhui",
            "region_name": "安徽",
            "manager": "李若楠",
            "target_amount": 2_100_000,
            "actual_amount": 640_000,
            "completion_rate": 0.3048,
            "pipeline_amount": 920_000,
            "win_rate": 0.182,
            "risk_level": "high",
            "main_issue": "客户结构偏长尾，缺少大额机会",
        },
    ]


def _sales_reps(period: str) -> list[dict[str, Any]]:
    period = _period_label(period)
    return [
        {
            "period": period,
            "rep_id": "rep-1001",
            "name": "王晨",
            "region_name": "上海",
            "target_amount": 1_600_000,
            "actual_amount": 1_520_000,
            "completion_rate": 0.95,
            "new_opportunities": 32,
            "proposal_count": 18,
            "contract_count": 7,
            "coaching_needed": False,
        },
        {
            "period": period,
            "rep_id": "rep-1002",
            "name": "顾宁",
            "region_name": "江苏",
            "target_amount": 1_300_000,
            "actual_amount": 480_000,
            "completion_rate": 0.3692,
            "new_opportunities": 17,
            "proposal_count": 5,
            "contract_count": 2,
            "coaching_needed": True,
        },
        {
            "period": period,
            "rep_id": "rep-1003",
            "name": "赵一帆",
            "region_name": "浙江",
            "target_amount": 1_100_000,
            "actual_amount": 710_000,
            "completion_rate": 0.6455,
            "new_opportunities": 24,
            "proposal_count": 10,
            "contract_count": 3,
            "coaching_needed": True,
        },
    ]


def _sales_opportunities(period: str) -> list[dict[str, Any]]:
    period = _period_label(period)
    return [
        {
            "period": period,
            "opportunity_id": "opp-202605-001",
            "customer_name": "海川装备集团",
            "region_name": "上海",
            "owner": "王晨",
            "expected_amount": 1_200_000,
            "stage": "legal_review",
            "expected_sign_date": "2026-05-30",
            "sign_probability": 0.72,
            "risk_level": "medium",
            "risk_reason": "法务条款仍在确认，若延期会影响本月目标约10个百分点。",
        },
        {
            "period": period,
            "opportunity_id": "opp-202605-002",
            "customer_name": "星河零售",
            "region_name": "江苏",
            "owner": "顾宁",
            "expected_amount": 1_500_000,
            "stage": "proposal_revision",
            "expected_sign_date": "2026-06-12",
            "sign_probability": 0.46,
            "risk_level": "high",
            "risk_reason": "预算审批未完成，签约时间大概率跨月。",
        },
        {
            "period": period,
            "opportunity_id": "opp-202605-003",
            "customer_name": "青云制造",
            "region_name": "安徽",
            "owner": "赵一帆",
            "expected_amount": 850_000,
            "stage": "decision_maker_meeting",
            "expected_sign_date": "2026-05-29",
            "sign_probability": 0.38,
            "risk_level": "high",
            "risk_reason": "关键决策人尚未确认方案价值，成交概率偏低。",
        },
    ]


@router.get("/target", response_model=ApiResponse)
async def get_sales_target(period: str = Query("current")) -> ApiResponse:
    return ApiResponse(data=_sales_target(period))


@router.get("/funnel", response_model=ApiResponse)
async def get_sales_funnel(period: str = Query("current")) -> ApiResponse:
    return ApiResponse(data=_sales_funnel(period))


@router.get("/regions", response_model=ApiResponse)
async def list_sales_regions(period: str = Query("current")) -> ApiResponse:
    return ApiResponse(data={"period": _period_label(period), "regions": _sales_regions(period)})


@router.get("/reps", response_model=ApiResponse)
async def list_sales_reps(period: str = Query("current")) -> ApiResponse:
    return ApiResponse(data={"period": _period_label(period), "sales_reps": _sales_reps(period)})


@router.get("/opportunities", response_model=ApiResponse)
async def list_sales_opportunities(period: str = Query("current")) -> ApiResponse:
    return ApiResponse(data={"period": _period_label(period), "opportunities": _sales_opportunities(period)})


@router.get("/snapshot", response_model=ApiResponse)
async def get_sales_review_snapshot(period: str = Query("current")) -> ApiResponse:
    period = _period_label(period)
    data = {
        "period": period,
        "target": _sales_target(period),
        "funnel": _sales_funnel(period),
        "regions": _sales_regions(period),
        "sales_reps": _sales_reps(period),
        "key_opportunities": _sales_opportunities(period),
        "expected_review_output": "目标差距-核心原因-分层行动计划",
    }
    return ApiResponse(data=data)

