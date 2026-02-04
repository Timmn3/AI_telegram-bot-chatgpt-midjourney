# tools/force_pay.py
from __future__ import annotations

import argparse
import asyncio


async def main(order_id: str) -> None:
    # Берём те же модули, что и твой API сервер
    import api_server  # где объявлен process_pay (см. ChatGpt.txt: FILE: api_server.py)
    from utils import db  # utils.db.get_order()

    order = await db.get_order(order_id)
    if order is None:
        print(f"❌ Order not found: {order_id}")
        return

    pay_time = order.get("pay_time")
    amount = order.get("amount")

    print("== ORDER ==")
    print(f"order_id : {order_id}")
    print(f"user_id  : {order.get('user_id')}")
    print(f"type     : {order.get('order_type')}")
    print(f"qty      : {order.get('quantity')}")
    print(f"amount   : {amount}")
    print(f"pay_time : {pay_time}")

    # ВАЖНО: если pay_time уже стоит — process_purchase() сразу return и начисления не будет
    # (см. условие if order['pay_time']: return)
    if pay_time:
        print("\n⚠️ pay_time уже заполнен. Начисление НЕ пройдет, пока не сделаешь pay_time = NULL в orders.")
        print("SQL:\nUPDATE orders SET pay_time = NULL WHERE order_id = '<order_id>';")
        return

    if amount is None:
        print("❌ В заказе нет amount — не могу имитировать оплату.")
        return

    # В твоём коде amount приводится к int при вызове process_pay
    await api_server.process_pay(order_id, int(amount))
    print("\n✅ OK: process_pay выполнен (оплата зачтена и обработчик вызван).")


if __name__ == "__main__":
    order_id = "424021b1-044d-43bb-95fe-f9cadcfa95f4"

    asyncio.run(main(order_id))
