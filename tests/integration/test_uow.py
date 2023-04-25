# pylint: disable=broad-except
import threading
import time
import traceback
from typing import List
import pytest
from sqlalchemy.sql import delete, insert, select, text

from allocation.adapters.orm import allocations, batches, products, order_lines
from allocation.domain import model
from allocation.service_layer import unit_of_work
from ..random_refs import random_sku, random_batchref, random_orderid


def insert_batch(session, ref, sku, qty, eta, product_version=1):
    # session.execute(
    #     "INSERT INTO products (sku, version_number) VALUES (:sku, :version)",
    #     dict(sku=sku, version=product_version),
    # )
    session.execute(insert(products).values(sku=sku, version_number=product_version))
    # session.execute(
    #     "INSERT INTO batches (reference, sku, _purchased_quantity, eta)"
    #     " VALUES (:ref, :sku, :qty, :eta)",
    #     dict(ref=ref, sku=sku, qty=qty, eta=eta),
    # )
    session.execute(
        insert(batches).values(reference=ref, sku=sku, _purchased_quantity=qty, eta=eta)
    )


def get_allocated_batch_ref(session, orderid, sku):
    # [[orderlineid]] = session.execute(
    #     "SELECT id FROM order_lines WHERE orderid=:orderid AND sku=:sku",
    #     dict(orderid=orderid, sku=sku),
    # )

    # SQLAlchemy ORM approach
    orderline = session.scalars(
        select(model.OrderLine)
        .where(model.OrderLine.orderid == orderid)
        .where(model.OrderLine.sku == sku)
    ).first()

    orderlineid = orderline.orderid

    # [[batchref]] = session.execute(
    #     "SELECT b.reference FROM allocations JOIN batches AS b ON batch_id = b.id"
    #     " WHERE orderline_id=:orderlineid",
    #     dict(orderlineid=orderlineid),
    # )

    # SQLAlchmey 2.x join_from
    # https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html#setting-the-leftmost-from-clause-in-a-join
    stmt = (
        select(model.Batch.reference)
        .join_from(allocations, batches)
        .where(model.OrderLine.orderid == orderlineid)
    )

    # execute the prepared statement and take the first returned record
    batchref = session.execute(stmt).scalars().first()
    session.close()

    return batchref


def test_uow_can_retrieve_a_batch_and_allocate_to_it(session_factory):
    session = session_factory
    insert_batch(session, "batch1", "SEABREEZE", 100, None)
    session.commit()

    uow = unit_of_work.SqlAlchemyUnitOfWork(session_factory)
    with uow:
        product = uow.products.get(sku="SEABREEZE")
        line = model.OrderLine("o1", "SEABREEZE", 10)
        product.allocate(line)
        uow.commit()

    batchref = get_allocated_batch_ref(session, "o1", "SEABREEZE")
    assert batchref == "batch1"
    session.close()


def test_rolls_back_uncommitted_work_by_default(session_factory):
    uow = unit_of_work.SqlAlchemyUnitOfWork(session_factory)
    with uow:
        insert_batch(uow.session, "batch1", "NIGHTCLUB", 100, None)

    new_session = session_factory
    rows = list(new_session.execute(text('SELECT * FROM "batches"')))
    assert rows == []
    session_factory.close()
    new_session.close()


def test_rolls_back_on_error(session_factory):
    class MyException(Exception):
        pass

    uow = unit_of_work.SqlAlchemyUnitOfWork(session_factory)
    with pytest.raises(MyException):
        with uow:
            insert_batch(uow.session, "batch1", "FOREST", 100, None)
            raise MyException()

    new_session = session_factory
    rows = list(new_session.execute(text('SELECT * FROM "batches"')))
    assert rows == []
    session_factory.close()
    new_session.close()


def try_to_allocate(orderid, sku, exceptions):
    line = model.OrderLine(orderid, sku, 10)
    try:
        with unit_of_work.SqlAlchemyUnitOfWork() as uow:
            product = uow.products.get(sku=sku)
            product.allocate(line)
            time.sleep(0.2)
            uow.commit()
    except Exception as e:
        print(traceback.format_exc())
        exceptions.append(e)


def test_concurrent_updates_to_version_are_not_allowed(session_factory):
    # this test is irrelevant if we are using SQLite
    pass
    # sku, batch = random_sku(), random_batchref()
    # session = session_factory
    # insert_batch(session, batch, sku, 100, eta=None, product_version=1)
    # session.commit()

    # order1, order2 = random_orderid(1), random_orderid(2)
    # exceptions = []  # type: List[Exception]
    # try_to_allocate_order1 = lambda: try_to_allocate(order1, sku, exceptions)
    # try_to_allocate_order2 = lambda: try_to_allocate(order2, sku, exceptions)
    # thread1 = threading.Thread(target=try_to_allocate_order1)
    # thread2 = threading.Thread(target=try_to_allocate_order2)
    # thread1.start()
    # thread2.start()
    # thread1.join()
    # thread2.join()

    # # [[version]] = session.execute(
    # #     "SELECT version_number FROM products WHERE sku=:sku",
    # #     dict(sku=sku),
    # # )

    # version = session.scalars(
    #     select(model.Product.version_number).where(model.Product.sku == sku)
    # ).first()

    # print(f"==============================")
    # print(f"VERSION: {version}")
    # print(f"==============================")

    # # assert version == 2
    # # [exception] = exceptions
    # # assert "could not serialize access due to concurrent update" in str(exception)

    # # orders = session.execute(
    # #     "SELECT orderid FROM allocations"
    # #     " JOIN batches ON allocations.batch_id = batches.id"
    # #     " JOIN order_lines ON allocations.orderline_id = order_lines.id"
    # #     " WHERE order_lines.sku=:sku",
    # #     dict(sku=sku),
    # # )

    # # [[batchref]] = session.execute(
    # #     "SELECT b.reference FROM allocations JOIN batches AS b ON batch_id = b.id"
    # #     " WHERE orderline_id=:orderlineid",
    # #     dict(orderlineid=orderlineid),
    # # )

    # # SQLAlchmey 2.x join_from
    # # https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html#setting-the-leftmost-from-clause-in-a-join
    # stmt = (
    #     select(allocations.c.orderid)
    #     .join_from(allocations, batches)
    #     .join_from(order_lines, allocations)
    #     .where(model.OrderLine.sku == sku)
    # )

    # print(f"==============================")
    # print(stmt)
    # print(f"==============================")

    # # execute the prepared statement and take the first returned record
    # orders = session.execute(stmt).scalars()
    # session.close()

    # assert orders.rowcount == 1
    # with unit_of_work.SqlAlchemyUnitOfWork() as uow:
    #     uow.session.execute("select 1")
