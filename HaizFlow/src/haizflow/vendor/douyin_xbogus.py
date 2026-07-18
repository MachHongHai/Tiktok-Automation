# Copyright (C) 2021 Evil0ctal
#
# Derived from Douyin_TikTok_Download_API and the jiji262/douyin-downloader
# project. Licensed under the Apache License, Version 2.0.

import base64
import hashlib
import time


class XBogus:
    def __init__(self, user_agent: str) -> None:
        self._array = [None] * 48 + list(range(10)) + [None] * 39 + list(range(10, 16))
        self._character = "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe="
        self._ua_key = b"\x00\x01\x0c"
        self._user_agent = user_agent

    def _md5_str_to_array(self, value: str) -> list[int]:
        if len(value) > 32:
            return [ord(character) for character in value]
        result = []
        for index in range(0, len(value), 2):
            result.append((self._array[ord(value[index])] << 4) | self._array[ord(value[index + 1])])
        return result

    def _md5(self, value: str | list[int]) -> str:
        data = self._md5_str_to_array(value) if isinstance(value, str) else value
        return hashlib.md5(bytes(data)).hexdigest()

    def _md5_encrypt(self, value: str) -> list[int]:
        return self._md5_str_to_array(self._md5(self._md5_str_to_array(self._md5(value))))

    @staticmethod
    def _rc4_encrypt(key: bytes, data: bytes) -> bytearray:
        state = list(range(256))
        position = 0
        for index in range(256):
            position = (position + state[index] + key[index % len(key)]) % 256
            state[index], state[position] = state[position], state[index]
        left = right = 0
        encrypted = bytearray()
        for byte in data:
            left = (left + 1) % 256
            right = (right + state[left]) % 256
            state[left], state[right] = state[right], state[left]
            encrypted.append(byte ^ state[(state[left] + state[right]) % 256])
        return encrypted

    def _conversion(self, values: list[int]) -> str:
        first = values[::2]
        second = values[1::2]
        merged = first + second
        payload = [
            merged[0],
            int(merged[10]),
            merged[1],
            merged[11],
            merged[2],
            merged[12],
            merged[3],
            merged[13],
            merged[4],
            merged[14],
            merged[5],
            merged[15],
            merged[6],
            merged[16],
            merged[7],
            merged[17],
            merged[8],
            merged[18],
            merged[9],
        ]
        return bytes(payload).decode("latin-1")

    def _calculation(self, first: int, second: int, third: int) -> str:
        value = ((first & 255) << 16) | ((second & 255) << 8) | (third & 255)
        return (
            self._character[(value & 16515072) >> 18]
            + self._character[(value & 258048) >> 12]
            + self._character[(value & 4032) >> 6]
            + self._character[value & 63]
        )

    def build(self, url: str) -> tuple[str, str, str]:
        ua_hash = self._md5_str_to_array(
            self._md5(base64.b64encode(self._rc4_encrypt(self._ua_key, self._user_agent.encode("latin-1"))).decode("latin-1"))
        )
        empty_hash = self._md5_str_to_array(
            self._md5(self._md5_str_to_array("d41d8cd98f00b204e9800998ecf8427e"))
        )
        url_hash = self._md5_encrypt(url)
        timestamp = int(time.time())
        constant = 536919696
        values = [
            64,
            0,
            1,
            12,
            url_hash[14],
            url_hash[15],
            empty_hash[14],
            empty_hash[15],
            ua_hash[14],
            ua_hash[15],
            timestamp >> 24 & 255,
            timestamp >> 16 & 255,
            timestamp >> 8 & 255,
            timestamp & 255,
            constant >> 24 & 255,
            constant >> 16 & 255,
            constant >> 8 & 255,
            constant & 255,
        ]
        checksum = values[0]
        for value in values[1:]:
            checksum ^= int(value)
        values.append(checksum)
        encoded = chr(2) + chr(255) + self._rc4_encrypt(
            bytes([255]), self._conversion(values).encode("latin-1")
        ).decode("latin-1")
        signature = "".join(
            self._calculation(ord(encoded[index]), ord(encoded[index + 1]), ord(encoded[index + 2]))
            for index in range(0, len(encoded), 3)
        )
        return f"{url}&X-Bogus={signature}", signature, self._user_agent
