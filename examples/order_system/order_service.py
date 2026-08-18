"""订单管理系统 — 核心业务模块示例。"""
import json
from datetime import datetime
from decimal import Decimal


class Order:
    """订单实体：包含订单号、金额与状态。"""

    def __init__(self, order_id: str, amount: Decimal, customer: str):
        self.order_id = order_id
        self.amount = amount
        self.customer = customer
        self.status = "pending"

    def confirm(self) -> None:
        """确认订单，状态改为 confirmed。"""
        if self.status != "pending":
            raise ValueError(f"订单 {self.order_id} 当前状态不允许确认: {self.status}")
        self.status = "confirmed"

    def cancel(self, reason: str) -> None:
        """取消订单并记录原因。"""
        self.status = "cancelled"
        self.cancel_reason = reason


class OrderService:
    """订单服务：负责订单的创建、确认与查询。"""

    def __init__(self, repository):
        self.repository = repository

    def create_order(self, order_id: str, amount: Decimal, customer: str) -> Order:
        order = Order(order_id, amount, customer)
        self.repository.save(order)
        return order

    def confirm_order(self, order_id: str) -> Order:
        order = self.repository.find(order_id)
        if order is None:
            raise KeyError(f"订单不存在: {order_id}")
        order.confirm()
        self.repository.save(order)
        return order

    def list_orders(self, customer: str = None) -> list:
        orders = self.repository.all()
        if customer:
            return [o for o in orders if o.customer == customer]
        return orders


def serialize_order(order: Order) -> dict:
    """将订单序列化为 JSON 友好的字典。"""
    return {
        "order_id": order.order_id,
        "amount": str(order.amount),
        "customer": order.customer,
        "status": order.status,
        "created_at": datetime.now().isoformat(),
    }
