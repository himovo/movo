"""A duplicate request observes the original attempt instead of executing again."""
import asyncio


async def wait_for_receipt(repository, key):
    while True:
        receipt = await repository.receipt_by_idempotency(key)
        if receipt is None:
            raise LookupError('Execution receipt disappeared')
        if receipt.status != 'running':
            return receipt
        await asyncio.sleep(.1)
