# Copyright (C) PhcNguyen Developers
# Distributed under the terms of the Modified BSD License.

import os
import time
import json
import base64
import typing
import hashlib

from src.security import rsa
from src.model.types import DBManager
from src.model.settings import AlgorithmSettings
from src.manager.key import (
    isAnotherKeyServer,
)


class AlgorithmHandler(AlgorithmSettings):
    def __init__(self, sql: DBManager) -> None:
        self.sql = sql

        self.public_key = None
        self.private_key = None

        self.message_callback = None

         # Khởi tạo cặp khóa RSA
        self._initialize_RsaKeys()
    
    def _initialize_RsaKeys(self):
        """Kiểm tra và tạo cặp khóa RSA nếu chưa tồn tại."""

        if not (os.path.exists(self.key_path["public"]) 
        and os.path.exists(self.key_path["private"])
        ):  
            """Tạo cặp khóa RSA mới và lưu vào file."""
            try:
                self._notify("Create a new RSA key pair and save it to a file.")
                self.public_key, self.private_key = rsa.newkeys(512)  # Tạo cặp khóa 512-bit

                with open(self.key_path["public"], "wb") as pub_file, \
                    open(self.key_path["private"], "wb") as priv_file:
                    pub_file.write(self.public_key.save_pkcs1())
                    priv_file.write(self.private_key.save_pkcs1())  

            except Exception as error:
                self._notify_error(f"Error creating a key: {error}")
        
        """Tải khóa RSA từ file."""
        try:
            self._notify("Download the RSA key from the file.")

            with open(self.key_path["public"], "rb") as pub_file, \
                 open(self.key_path["private"], "rb") as priv_file:
                self.public_key = rsa.PublicKey.load_pkcs1(pub_file.read())
                self.private_key = rsa.PrivateKey.load_pkcs1(priv_file.read())

        except Exception as error:
            self._notify_error(f"Error loading the lock: {error}")
    
    def _notify(self, message):
        """Notification method."""
        if self.message_callback:
            self.message_callback(f"Error: {message}")
    
    def _notify_error(self, message):
        """Error notification method."""
        if self.message_callback:
            self.message_callback(f"Error: {message}")

    @staticmethod
    def generate_id(string: str) -> str:
        """Tạo chuỗi hash SHA-256 từ input string và timestamp."""
        hash_bytes = hashlib.sha256(f"{string}-{int(time.time() * 1000)}".encode()).digest()
        # Mã hóa hash thành chuỗi base64 và loại bỏ ký tự "="
        return base64.urlsafe_b64encode(hash_bytes).rstrip(b"=").decode()
    
    def set_message_callback(
        self, callback: 
        typing.Callable[[str], None]
    ):  self.message_callback = callback

    def handle_data(
        self, 
        client_address: tuple, 
        client_data: bytes
    ) -> bytes:
        """Xử lý dữ liệu từ client và trả về kết quả."""
        data = decrypted_data(client_data, self.public_key, self.private_key)

        # GET DATA 
        action = data.get("action", "Unknown")
        message = data.get("message", "Unknown")

        pub_key_client = data.get("pub_key_client", "Unknown")
        pub_key_server = data.get("pub_key_client", "Unknown")
        
        if 'status' in data:
            return data

        # Kiểm tra xem public_key_server đúng không
        if not isAnotherKeyServer(self.public_key, pub_key_server):
            result = {
                "status": True,
                "pub_key_server": self.public_key,
                "message": "This is your Public Key"
            }
            return json.dumps(result).encode("utf-8")
        
        

        if action == "Unknown":
            result = {
                "status": True,
                "pub_key_server": self.public_key,
                "message": "This is your Public Key"
            }
            return json.dumps(result).encode("utf-8")


def decrypted_data(
    client_data: bytes,
    public_key: rsa.PublicKey, 
    private_key: rsa.PrivateKey
) -> typing.Dict:
    """Giải mã dữ liệu."""
    try:
        decrypted_data = rsa.decrypt(client_data, private_key)
        data = decrypted_data.decode("utf-8")
        data = json.loads(data)
        # Kiểm tra định dạng data có đúng là dict không
        if not isinstance(data, dict):
            return {
                "status": False,
                "pub_key_server": public_key,
                "message": "Invalid data format"
            }
    except (rsa.DecryptionError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return {
            "status": False,
            "pub_key_server": public_key,
            "message": str(e)
        }
    
    return data