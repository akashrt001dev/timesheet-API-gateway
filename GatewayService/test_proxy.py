import httpx
import asyncio
import traceback

async def test_async():
    try:
        async with httpx.AsyncClient(verify=False, timeout=5.0) as client:
            r = await client.get('http://host.docker.internal:8001/user/642472ce1a6c0d4b84d5439a')
            print(f'Async - Status: {r.status_code}')
    except Exception as e:
        print(f'Async error: {type(e).__name__}: {str(e)}')
        traceback.print_exc()

def test_sync():
    try:
        with httpx.Client(verify=False, timeout=5.0) as client:
            r = client.get('http://host.docker.internal:8001/user/642472ce1a6c0d4b84d5439a')
            print(f'Sync - Status: {r.status_code}')
    except Exception as e:
        print(f'Sync error: {type(e).__name__}: {str(e)}')
        traceback.print_exc()

if __name__ == '__main__':
    test_sync()
    asyncio.run(test_async())
