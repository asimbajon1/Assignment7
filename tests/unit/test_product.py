from datetime import date, timedelta
import pytest
from allocation.domain.model import Product, OrderLine, Batch, OutOfStock

today = date.today()
tomorrow = today + timedelta(days=1)
later = tomorrow + timedelta(days=10)


def test_prefers_warehouse_batches_to_shipments():
    in_stock_batch = Batch("in-stock-batch", "RETRO-CLOCK", 100, eta=None)
    shipment_batch = Batch("shipment-batch", "RETRO-CLOCK", 100, eta=tomorrow)
    product = Product(sku="RETRO-CLOCK", batches=[in_stock_batch, shipment_batch])
    line = OrderLine("oref", "RETRO-CLOCK", 10)

    product.allocate(line)

    assert in_stock_batch.available_quantity == 90
    assert shipment_batch.available_quantity == 100


def test_prefers_earlier_batches():
    earliest = Batch("speedy-batch", "SEABREEZE", 100, eta=today)
    medium = Batch("normal-batch", "SEABREEZE", 100, eta=tomorrow)
    latest = Batch("slow-batch", "SEABREEZE", 100, eta=later)
    product = Product(sku="SEABREEZE", batches=[medium, earliest, latest])
    line = OrderLine("order1", "SEABREEZE", 10)

    product.allocate(line)

    assert earliest.available_quantity == 90
    assert medium.available_quantity == 100
    assert latest.available_quantity == 100


def test_returns_allocated_batch_ref():
    in_stock_batch = Batch("in-stock-batch-ref", "NIGHTCLUB", 100, eta=None)
    shipment_batch = Batch("shipment-batch-ref", "NIGHTCLUB", 100, eta=tomorrow)
    line = OrderLine("oref", "NIGHTCLUB", 10)
    product = Product(sku="NIGHTCLUB", batches=[in_stock_batch, shipment_batch])
    allocation = product.allocate(line)
    assert allocation == in_stock_batch.reference


def test_raises_out_of_stock_exception_if_cannot_allocate():
    batch = Batch("batch1", "JUNGLE", 10, eta=today)
    product = Product(sku="JUNGLE", batches=[batch])
    product.allocate(OrderLine("order1", "JUNGLE", 10))

    with pytest.raises(OutOfStock, match="JUNGLE"):
        product.allocate(OrderLine("order2", "JUNGLE", 1))


def test_increments_version_number():
    line = OrderLine("oref", "FOREST", 10)
    product = Product(
        sku="FOREST", batches=[Batch("b1", "FOREST", 100, eta=None)]
    )
    product.version_number = 7
    product.allocate(line)
    assert product.version_number == 8
