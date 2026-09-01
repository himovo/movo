from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/mock/store-diagnosis", tags=["mock-store-diagnosis"])


class ApiResponse(BaseModel):
    code: int = 0
    message: Optional[str] = None
    data: Optional[object] = None


def _period_label(period: str) -> str:
    if period == "current":
        return "2026-06"
    return period or "2026-06"


def _store_operating_snapshot(period: str) -> dict[str, Any]:
    period = _period_label(period)
    return {
        "period": period,
        "scope": "华东直营门店",
        "currency": "CNY",
        "diagnostic_policy": {
            "name": "直营门店经营异常诊断口径",
            "source": "mock knowledge base",
            "notes": "门店异常需同时参考销售达成、客流变化、库存周转和活动投入产出；单项异常不直接等同经营风险。",
            "thresholds": {
                "sales_completion_low": 0.85,
                "traffic_decline_high": -0.12,
                "inventory_turnover_days_high": 45,
                "campaign_roi_low": 1.2,
            },
        },
        "stores": [
            {
                "store_id": "store-sh-xuhui",
                "store_name": "上海徐汇店",
                "city": "上海",
                "manager": "林悦",
                "sales": {
                    "target_amount": 1_200_000,
                    "actual_amount": 1_080_000,
                    "completion_rate": 0.90,
                    "month_over_month_change": -0.03,
                },
                "traffic": {
                    "visitor_count": 34_200,
                    "month_over_month_change": -0.04,
                    "conversion_rate": 0.198,
                    "historical_avg_conversion_rate": 0.205,
                },
                "inventory": {
                    "stock_amount": 740_000,
                    "turnover_days": 32,
                    "slow_moving_sku_count": 18,
                    "stockout_sku_count": 4,
                },
                "campaigns": [
                    {
                        "campaign_name": "会员日满减",
                        "cost": 58_000,
                        "incremental_sales": 96_000,
                        "roi": 1.66,
                    }
                ],
                "known_context": "核心商圈客流稳定，近期无重大装修或竞品开业影响。",
            },
            {
                "store_id": "store-sh-pudong",
                "store_name": "上海浦东店",
                "city": "上海",
                "manager": "周岩",
                "sales": {
                    "target_amount": 1_500_000,
                    "actual_amount": 1_020_000,
                    "completion_rate": 0.68,
                    "month_over_month_change": -0.18,
                },
                "traffic": {
                    "visitor_count": 28_500,
                    "month_over_month_change": -0.21,
                    "conversion_rate": 0.184,
                    "historical_avg_conversion_rate": 0.213,
                },
                "inventory": {
                    "stock_amount": 920_000,
                    "turnover_days": 39,
                    "slow_moving_sku_count": 31,
                    "stockout_sku_count": 9,
                },
                "campaigns": [
                    {
                        "campaign_name": "商圈拉新券",
                        "cost": 96_000,
                        "incremental_sales": 82_000,
                        "roi": 0.85,
                    }
                ],
                "known_context": "周边新开同业门店，工作日午后客流下降明显。",
            },
            {
                "store_id": "store-hz-westlake",
                "store_name": "杭州西湖店",
                "city": "杭州",
                "manager": "陈敏",
                "sales": {
                    "target_amount": 1_000_000,
                    "actual_amount": 940_000,
                    "completion_rate": 0.94,
                    "month_over_month_change": 0.02,
                },
                "traffic": {
                    "visitor_count": 31_800,
                    "month_over_month_change": 0.03,
                    "conversion_rate": 0.191,
                    "historical_avg_conversion_rate": 0.188,
                },
                "inventory": {
                    "stock_amount": 1_180_000,
                    "turnover_days": 58,
                    "slow_moving_sku_count": 64,
                    "stockout_sku_count": 2,
                },
                "campaigns": [
                    {
                        "campaign_name": "夏季新品陈列",
                        "cost": 42_000,
                        "incremental_sales": 89_000,
                        "roi": 2.12,
                    }
                ],
                "known_context": "销售与客流基本正常，但新品与旧款库存结构失衡。",
            },
            {
                "store_id": "store-nj-xinjiekou",
                "store_name": "南京新街口店",
                "city": "南京",
                "manager": "王珂",
                "sales": {
                    "target_amount": 900_000,
                    "actual_amount": 620_000,
                    "completion_rate": 0.689,
                    "month_over_month_change": -0.09,
                },
                "traffic": {
                    "visitor_count": 25_400,
                    "month_over_month_change": -0.06,
                    "conversion_rate": 0.142,
                    "historical_avg_conversion_rate": 0.196,
                },
                "inventory": {
                    "stock_amount": 640_000,
                    "turnover_days": 35,
                    "slow_moving_sku_count": 22,
                    "stockout_sku_count": 17,
                },
                "campaigns": [
                    {
                        "campaign_name": "周末组合购",
                        "cost": 51_000,
                        "incremental_sales": 70_000,
                        "roi": 1.37,
                    }
                ],
                "known_context": "客流降幅不大，但成交率明显低于历史均值，畅销 SKU 缺货较多。",
            },
            {
                "store_id": "store-sz-industrial-park",
                "store_name": "苏州园区店",
                "city": "苏州",
                "manager": "赵宁",
                "sales": {
                    "target_amount": 760_000,
                    "actual_amount": 790_000,
                    "completion_rate": 1.039,
                    "month_over_month_change": 0.07,
                },
                "traffic": {
                    "visitor_count": 19_600,
                    "month_over_month_change": 0.05,
                    "conversion_rate": 0.221,
                    "historical_avg_conversion_rate": 0.207,
                },
                "inventory": {
                    "stock_amount": 430_000,
                    "turnover_days": 27,
                    "slow_moving_sku_count": 9,
                    "stockout_sku_count": 6,
                },
                "campaigns": [
                    {
                        "campaign_name": "企业客户团购",
                        "cost": 35_000,
                        "incremental_sales": 118_000,
                        "roi": 3.37,
                    }
                ],
                "known_context": "企业团购带动明显，销售、客流、库存均处于健康区间。",
            },
        ],
        "expected_diagnostic_output": "门店异常清单-原因分支-处理优先级-总部统一行动建议",
    }


@router.get("/snapshot", response_model=ApiResponse)
async def get_store_diagnosis_snapshot(period: str = Query("current")) -> ApiResponse:
    return ApiResponse(data=_store_operating_snapshot(period))

