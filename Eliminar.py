import aiohttp
import asyncio
import json
import platform

SWITCH_TOKEN = "OThmN2U0MmMyZTNhNGY4NmE3NGViNDNmYmI0MWVkMzk6MGEyNDQ5YTItMDAxYS00NTFlLWFmZWMtM2U4MTI5MDFjNGQ3"
IOS_TOKEN = "MzQ0NmNkNzI2OTRjNGE0NDg1ZDgxYjc3YWRiYjIxNDE6OTIwOWQ0YTVlMjVhNDU3ZmI5YjA3NDg5ZDMxM2I0MWE="

class EpicUser:
    def __init__(self, data: dict = {}):
        self.raw = data

        self.access_token = data.get("access_token", "")
        self.account_id = data.get("account_id", "")
        self.display_name = data.get("displayName", "")

class EpicGenerator:
    def __init__(self) -> None:
        self.http: aiohttp.ClientSession
        self.user_agent = f"DeviceAuthGenerator/{platform.system()}/{platform.version()}"
        self.access_token = ""

    async def start(self) -> None:
        self.http = aiohttp.ClientSession(headers={"User-Agent": self.user_agent})
        self.access_token = await self.get_access_token()

    async def get_access_token(self) -> str:
        async with self.http.post(
            url="https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"basic {SWITCH_TOKEN}",
            },
            data={
                "grant_type": "client_credentials",
            },
        ) as response:
            data = await response.json()
            return data["access_token"]

    async def create_device_code(self) -> tuple:
        async with self.http.post(
            url="https://account-public-service-prod.ol.epicgames.com/account/api/oauth/deviceAuthorization",
            headers={
                "Authorization": f"bearer {self.access_token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        ) as response:
            data = await response.json()
            return data["verification_uri_complete"], data["device_code"]

    async def wait_for_device_code_completion(self, code: str) -> EpicUser:
        while True:
            async with self.http.post(
                url="https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token",
                headers={
                    "Authorization": f"basic {SWITCH_TOKEN}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "device_code", "device_code": code},
            ) as request:
                token = await request.json()

                if request.status == 200:
                    break
                else:
                    error_code = token.get("errorCode", "")
                    if error_code == "errors.com.epicgames.account.oauth.authorization_pending":
                        pass 
                    elif error_code == "errors.com.epicgames.account.oauth.authorization_expired":
                        print("La autorización del código del dispositivo ha expirado")
                        await self.close()
                        exit(1)
                    elif error_code == "errors.com.epicgames.common.slow_down":
                        print("Límite de velocidad de aciertos, disminuyendo la velocidad...")
                    else:
                        print(json.dumps(token, sort_keys=False, indent=4))
                        await self.close()
                        exit(1)
                await asyncio.sleep(11)

        async with self.http.get(
            url="https://account-public-service-prod.ol.epicgames.com/account/api/oauth/exchange",
            headers={"Authorization": f"bearer {token['access_token']}"},
        ) as request:
            exchange = await request.json()
        async with self.http.post(
            url="https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token",
            headers={
                "Authorization": f"basic {IOS_TOKEN}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "exchange_code",
                "exchange_code": exchange["code"],
                "token_type": "eg1",
            },
        ) as request:
            auth_information = await request.json()

            return EpicUser(data=auth_information)

    async def close(self):
        await self.http.close()

async def delete_friends(session: aiohttp.ClientSession, user: EpicUser):
    async with session.get(
        f"https://friends-public-service-prod.ol.epicgames.com/friends/api/public/friends/{user.account_id}",
        headers={"Authorization": f"bearer {user.access_token}"}
    ) as resp:
        if resp.status != 200:
            print(f"Error fetching friends list ({resp.status})")
            return
        friends = await resp.json()

    if not friends:
        print("No friends to delete.")
        return

    for friend in friends:
        friend_id = friend['accountId']
        async with session.delete(
            f"https://friends-public-service-prod.ol.epicgames.com/friends/api/public/friends/{user.account_id}/{friend_id}",
            headers={"Authorization": f"bearer {user.access_token}"}
        ) as resp:
            if resp.status != 204:
                print(f"Error al eliminar amiga {friend_id} ({resp.status})")
            else:
                print(f"Amigo {friend_id} Eliminado correctamente.")
        
        await asyncio.sleep(1)

async def main():
    epic_generator = EpicGenerator()
    try:
        await epic_generator.start()
        device_code_url, device_code = await epic_generator.create_device_code()
        print(f"Por favor autorice su cuenta visitando el siguiente enlace:\n{device_code_url}\n")
        print("Esperando que autorices...")

        user = await epic_generator.wait_for_device_code_completion(device_code)

        if not user.display_name or not user.account_id:
            print("No se pudo encontrar la información de tu amigo.")
            print("Información de autorización recibida:")
            print(json.dumps(user.raw, indent=4))
            return

        print(f"Autenticado como {user.display_name} ({user.account_id})")

        async with aiohttp.ClientSession() as session:
            await delete_friends(session, user)
            await session.close()
        print("Todos los amigos han sido eliminados de tu cuenta de Epic Games")
    finally:
        await epic_generator.close()

if __name__ == "__main__":
    asyncio.run(main())
