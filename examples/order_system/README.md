# 订单系统设计文档

## 概述
本系统用于管理客户订单，包含订单创建、确认、取消与查询功能。
系统由 Python 后端（order_service.py）与 MySQL 数据库（schema.sql）组成。

## 业务规则
- 订单状态流转：pending -> confirmed -> shipped -> completed
- 只有 pending 状态的订单可以被取消
- 订单金额使用 DECIMAL 存储，避免浮点误差

## 关键流程
1. 客户下单：OrderService.create_order 创建订单并保存
2. 商家确认：OrderService.confirm_order 校验状态后确认
3. 查询订单：按客户名过滤或列出全部订单

## 注意事项
- 序列化时金额转换为字符串，防止精度丢失
- 外键约束保证订单必须关联有效客户
