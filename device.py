# -*- coding: utf-8 -*-
"""Связь с iPhone по USB через pymobiledevice3: сведения об устройстве и снятие логов.
Поддерживает и старые (синхронные), и новые (асинхронные) версии pymobiledevice3.

Поток DeviceWatcher кладёт события в очередь:
  ("state", код, текст)  — код: nodriver | wait | trust | unlock | denied | error
  ("info", dev)          — телефон прочитан, начинается снятие логов
  ("pulled", dev)        — логи сняты, dev["dir"] — папка с логами
  ("disconnected", serial)
  ("erased", serial) / ("erase_failed", текст)
  ("log", текст)
"""

import asyncio
import inspect
import os
import queue
import re
import threading
import time

from core import logs_root
from knowledge_base import PRODUCTS


async def _ma(x):
    return await x if inspect.isawaitable(x) else x


def device_support():
    try:
        import pymobiledevice3  # noqa: F401
        return True
    except ImportError:
        return False


async def _list_usb_serials():
    from pymobiledevice3 import usbmux
    devs = await _ma(usbmux.list_devices())
    return [d.serial for d in devs if getattr(d, "connection_type", "USB") == "USB"]


async def _read_battery(lockdown, dev):
    try:
        from pymobiledevice3.services.diagnostics import DiagnosticsService
        bat = await _ma(DiagnosticsService(lockdown).get_battery()) or {}
    except Exception:
        return
    design = bat.get("DesignCapacity")
    full = bat.get("AppleRawMaxCapacity") or bat.get("NominalChargeCapacity")
    if design and full:
        dev["battery_health"] = round(full * 100 / design)
        dev["battery_mah"] = f"{full}/{design} mAh"
    dev["battery_cycles"] = bat.get("CycleCount")
    if bat.get("Temperature") is not None:
        dev["battery_temp"] = bat["Temperature"] / 100
    dev["battery_charge"] = bat.get("CurrentCapacity")
    dev["battery_serial"] = bat.get("Serial") or (bat.get("BatteryData") or {}).get("Serial")


async def _device_job(serial, out_root, on_info):
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.crash_reports import CrashReportsManager

    lockdown = await _ma(create_using_usbmux(serial=serial))
    v = getattr(lockdown, "all_values", {}) or {}
    product = v.get("ProductType", "")
    dev = {
        "udid": serial,
        "name": v.get("DeviceName", "") or "iPhone",
        "product": product,
        "model": PRODUCTS.get(product, product or "iPhone"),
        "ios": v.get("ProductVersion", ""),
        "build": v.get("BuildVersion", ""),
        "serial": v.get("SerialNumber", ""),
        "imei": v.get("InternationalMobileEquipmentIdentity", ""),
        "is_iphone": v.get("DeviceClass", "iPhone") == "iPhone",
        "baseband": v.get("BasebandVersion", ""),
        "hw_model": v.get("HardwareModel", ""),
        "wifi_mac": v.get("WiFiAddress", ""),
        "bt_mac": v.get("BluetoothAddress", ""),
    }
    await _read_battery(lockdown, dev)
    on_info(dev)

    safe = re.sub(r'[\\/:*?"<>|]+', "_", f'{dev["model"]}_{dev["serial"] or serial}')
    out_dir = os.path.join(out_root, safe)
    os.makedirs(out_dir, exist_ok=True)
    dev["dir"] = out_dir

    crm = CrashReportsManager(lockdown)
    try:
        await _ma(crm.flush())  # переносит свежие логи в папку CrashReports
    except Exception:
        pass
    try:
        await _ma(crm.pull(out_dir, erase=False, progress_bar=False))
    except TypeError:
        await _ma(crm.pull(out_dir, erase=False))
    try:
        await _ma(lockdown.close())
    except Exception:
        pass
    return dev


async def _erase_job(serial):
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.crash_reports import CrashReportsManager

    lockdown = await _ma(create_using_usbmux(serial=serial))
    await _ma(CrashReportsManager(lockdown).clear())
    try:
        await _ma(lockdown.close())
    except Exception:
        pass


class DeviceWatcher(threading.Thread):
    """Следит за подключением iPhone и сам снимает логи."""

    def __init__(self, events):
        super().__init__(daemon=True)
        self.events = events
        self.done = set()      # серийники, с которых уже сняли логи
        self.manual = queue.Queue()
        self.erase = queue.Queue()     # серийники (udid), на которых стереть логи
        self._last_state = None

    def state(self, code, text):
        if self._last_state != (code, text):
            self._last_state = (code, text)
            self.events.put(("state", code, text))

    def run(self):
        present = set()
        while True:
            try:
                serials = set(asyncio.run(_list_usb_serials()))
            except Exception as e:
                self.state("nodriver", e.__class__.__name__)
                time.sleep(4)
                continue

            for s in present - serials:
                self.events.put(("disconnected", s))
                self.done.discard(s)
                self._last_state = None
            present = serials
            if not serials:
                self.state("wait", "")

            while not self.erase.empty():
                s = self.erase.get()
                try:
                    asyncio.run(_erase_job(s))
                    self.events.put(("erased", s))
                except Exception as e:
                    self.events.put(("erase_failed", f"{e.__class__.__name__}: {e}"))

            again = set()
            while not self.manual.empty():
                again.add(self.manual.get())
            for s in serials:
                if s in again or "*" in again or s not in self.done:
                    self.process(s)
            time.sleep(2)

    def process(self, serial):
        try:
            dev = asyncio.run(_device_job(serial, logs_root(),
                                          lambda d: self.events.put(("info", d))))
            self.done.add(serial)
            self._last_state = None
            self.events.put(("pulled", dev))
        except Exception as e:
            name = e.__class__.__name__
            if "PairingDialog" in name or "NotPaired" in name or "NotTrusted" in name:
                self.state("trust", "")
            elif "PasswordRequired" in name:
                self.state("unlock", "")
            elif "UserDenied" in name:
                self.state("denied", "")
                self.done.add(serial)
            else:
                self.events.put(("log", f"{name}: {e}"))
                self.state("error", f"{name}: {e}")
                self.done.add(serial)
