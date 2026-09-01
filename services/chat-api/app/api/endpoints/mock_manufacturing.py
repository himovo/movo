from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/mock/manufacturing", tags=["mock-manufacturing"])


class ApiResponse(BaseModel):
    code: int = 0
    message: Optional[str] = None
    data: Optional[object] = None


def _period_label(period: str) -> str:
    if period in {"current", "this_month", ""}:
        return "2026-06"
    if period == "next_week":
        return "2026-W28"
    return period or "2026-06"


def _factory_context(period: str) -> dict[str, Any]:
    return {
        "period": _period_label(period),
        "factory": "苏州精密制造一厂",
        "currency": "CNY",
        "data_scope": "注塑、装配、包装三条主线",
        "mock_policy": {
            "name": "制造运营 E2E Mock 口径",
            "notes": "用于测试生产进度、交付风险、质量异常、设备停机和物料短缺的多工具编排。",
            "risk_thresholds": {
                "delivery_delay_days_high": 3,
                "material_ready_rate_low": 0.9,
                "defect_rate_high": 0.025,
                "line_load_rate_high": 0.95,
                "equipment_downtime_hours_high": 4,
            },
        },
    }


@router.get("/production-progress", response_model=ApiResponse)
async def get_production_progress(period: str = Query("current")) -> ApiResponse:
    context = _factory_context(period)
    context["lines"] = [
        {
            "line_id": "line-injection-a",
            "line_name": "注塑 A 线",
            "planned_qty": 12800,
            "actual_qty": 11120,
            "completion_rate": 0.869,
            "delayed_hours": 5.5,
            "bottleneck": "2 号注塑机换模后良率波动",
            "owner": "生产主管-周航",
        },
        {
            "line_id": "line-assembly-b",
            "line_name": "装配 B 线",
            "planned_qty": 9600,
            "actual_qty": 9480,
            "completion_rate": 0.988,
            "delayed_hours": 0.8,
            "bottleneck": "上午短时缺料，已恢复",
            "owner": "生产主管-刘倩",
        },
        {
            "line_id": "line-packaging-c",
            "line_name": "包装 C 线",
            "planned_qty": 8800,
            "actual_qty": 7420,
            "completion_rate": 0.843,
            "delayed_hours": 6.2,
            "bottleneck": "包装膜到料不足，夜班需补产",
            "owner": "生产主管-陈杰",
        },
    ]
    context["priority_work_orders"] = [
        {
            "work_order_id": "WO-202606-1842",
            "customer": "华东汽配客户 A",
            "sku": "ABS-HSG-210",
            "due_date": "2026-06-18",
            "planned_qty": 5000,
            "finished_qty": 3650,
            "status": "at_risk",
        },
        {
            "work_order_id": "WO-202606-1876",
            "customer": "深圳电子客户 C",
            "sku": "PBT-BKT-081",
            "due_date": "2026-06-20",
            "planned_qty": 3200,
            "finished_qty": 3180,
            "status": "normal",
        },
    ]
    return ApiResponse(data=context)


@router.get("/delivery-risk", response_model=ApiResponse)
async def get_delivery_risk(period: str = Query("current")) -> ApiResponse:
    context = _factory_context(period)
    context["orders"] = [
        {
            "order_id": "SO-202606-0931",
            "customer": "华东汽配客户 A",
            "sku": "ABS-HSG-210",
            "order_qty": 5000,
            "produced_qty": 3650,
            "due_date": "2026-06-18",
            "material_ready_rate": 0.82,
            "capacity_slot": "需占用注塑 A 线夜班",
            "risk_level": "high",
            "risk_reason": "注塑良率波动叠加关键树脂到料不足",
            "owner": "交付经理-王敏",
        },
        {
            "order_id": "SO-202606-0978",
            "customer": "浙江家电客户 B",
            "sku": "PP-CVR-033",
            "order_qty": 7200,
            "produced_qty": 6680,
            "due_date": "2026-06-19",
            "material_ready_rate": 0.94,
            "capacity_slot": "包装 C 线白班",
            "risk_level": "medium",
            "risk_reason": "包装膜缺口可能影响尾批入库",
            "owner": "交付经理-王敏",
        },
        {
            "order_id": "SO-202606-1012",
            "customer": "深圳电子客户 C",
            "sku": "PBT-BKT-081",
            "order_qty": 3200,
            "produced_qty": 3180,
            "due_date": "2026-06-20",
            "material_ready_rate": 1.0,
            "capacity_slot": "装配 B 线",
            "risk_level": "low",
            "risk_reason": "仅剩尾数检验与包装",
            "owner": "交付经理-李沐",
        },
    ]
    return ApiResponse(data=context)


@router.get("/material-shortage", response_model=ApiResponse)
async def get_material_shortage(period: str = Query("current")) -> ApiResponse:
    context = _factory_context(period)
    context["materials"] = [
        {
            "material_code": "RM-ABS-750K",
            "material_name": "ABS 树脂 750K",
            "on_hand_qty": 820,
            "reserved_qty": 760,
            "safety_stock": 1200,
            "shortage_qty": 1140,
            "affected_orders": ["SO-202606-0931"],
            "supplier": "昆山高分子材料",
            "eta": "2026-06-17 16:00",
            "recommendation": "提前拆分到料批次，优先保障 WO-202606-1842。",
        },
        {
            "material_code": "PK-FILM-450",
            "material_name": "450mm 包装膜",
            "on_hand_qty": 58,
            "reserved_qty": 54,
            "safety_stock": 100,
            "shortage_qty": 76,
            "affected_orders": ["SO-202606-0978"],
            "supplier": "苏州包装辅料",
            "eta": "2026-06-18 10:00",
            "recommendation": "确认替代规格可用性，并安排夜班补包装。",
        },
    ]
    return ApiResponse(data=context)


@router.get("/quality-defects", response_model=ApiResponse)
async def get_quality_defects(period: str = Query("current")) -> ApiResponse:
    context = _factory_context(period)
    context["quality_summary"] = {
        "overall_defect_rate": 0.023,
        "high_risk_process": "注塑成型",
        "top_defect_types": [
            {"defect": "缩水", "count": 86, "rate": 0.009},
            {"defect": "飞边", "count": 62, "rate": 0.0065},
            {"defect": "装配卡扣松动", "count": 39, "rate": 0.0041},
        ],
    }
    context["batches"] = [
        {
            "batch_id": "BATCH-ABS-210-0615-A",
            "line_name": "注塑 A 线",
            "sku": "ABS-HSG-210",
            "defect_rate": 0.038,
            "suspected_root_cause": "模温波动与换模后首件确认不足",
            "containment_action": "暂停尾批放行，复核模温曲线并加严首件检验。",
            "owner": "质量工程师-赵琳",
        },
        {
            "batch_id": "BATCH-PBT-081-0615-B",
            "line_name": "装配 B 线",
            "sku": "PBT-BKT-081",
            "defect_rate": 0.011,
            "suspected_root_cause": "卡扣工位扭矩偏低",
            "containment_action": "抽检已完成，调高扭矩标准。",
            "owner": "质量工程师-赵琳",
        },
    ]
    return ApiResponse(data=context)


@router.get("/equipment-downtime", response_model=ApiResponse)
async def get_equipment_downtime(period: str = Query("current")) -> ApiResponse:
    context = _factory_context(period)
    context["equipment"] = [
        {
            "equipment_id": "IMM-A02",
            "equipment_name": "2 号注塑机",
            "line_name": "注塑 A 线",
            "downtime_hours": 5.2,
            "fault_type": "液压温控异常",
            "impact_qty": 920,
            "repair_status": "temporary_fixed",
            "next_action": "夜班低速运行，明早安排供应商复检。",
        },
        {
            "equipment_id": "PKG-C04",
            "equipment_name": "4 号自动封膜机",
            "line_name": "包装 C 线",
            "downtime_hours": 2.1,
            "fault_type": "热封温度不稳定",
            "impact_qty": 430,
            "repair_status": "monitoring",
            "next_action": "更换温控探头备件，观察 2 小时。",
        },
    ]
    return ApiResponse(data=context)


@router.get("/capacity-load", response_model=ApiResponse)
async def get_capacity_load(period: str = Query("next_week")) -> ApiResponse:
    context = _factory_context(period)
    context["capacity"] = [
        {
            "line_name": "注塑 A 线",
            "available_hours": 108,
            "required_hours": 119,
            "load_rate": 1.102,
            "bottleneck": "ABS-HSG-210 与 PP-CVR-033 争用换模窗口",
            "suggestion": "增加 1 个夜班并调整 PP-CVR-033 至注塑备线。",
        },
        {
            "line_name": "装配 B 线",
            "available_hours": 96,
            "required_hours": 82,
            "load_rate": 0.854,
            "bottleneck": "无明显瓶颈",
            "suggestion": "可承接部分返工复检任务。",
        },
        {
            "line_name": "包装 C 线",
            "available_hours": 90,
            "required_hours": 93,
            "load_rate": 1.033,
            "bottleneck": "包装膜供应节奏不足",
            "suggestion": "将 SO-202606-0978 尾批包装排至夜班。",
        },
    ]
    return ApiResponse(data=context)
