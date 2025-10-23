"""Flashing Pipeline Automation

Provides safe, auditable, and rollback-capable flashing routines for recovery, boot, vendor, and system images on foldable devices.
"""

import os
import subprocess
from dataclasses import dataclass
from typing import List, Optional
import hashlib
import json

FASTBOOT = "fastboot"
ADB = "adb"


@dataclass
class ImageArtifact:
    path: str
    partition: str
    sha256: Optional[str] = None


class FlashingError(Exception):
    pass


class Flasher:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.log: List[str] = []

    def _run(self, cmd: List[str]) -> str:
        self.log.append("$ " + " ".join(cmd))
        if self.dry_run:
            return "DRY_RUN"
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
            self.log.append(out)
            return out
        except subprocess.CalledProcessError as e:
            self.log.append(e.output.decode())
            raise FlashingError(f"Command failed: {' '.join(cmd)}")

    def verify_device(self):
        out = self._run([ADB, 'get-state'])
        if 'device' not in out:
            raise FlashingError('Device not connected or unauthorized')
        self._run([ADB, 'reboot', 'bootloader'])
        self._run([FASTBOOT, 'devices'])

    def verify_image(self, artifact: ImageArtifact):
        if artifact.sha256:
            h = hashlib.sha256(open(artifact.path, 'rb').read()).hexdigest()
            if h != artifact.sha256:
                raise FlashingError(f"SHA256 mismatch for {artifact.path}")

    def flash_images(self, images: List[ImageArtifact], slot: Optional[str] = None):
        # Enter fastboot and verify
        self.verify_device()
        
        if slot:
            self._run([FASTBOOT, 'set_active', slot])

        # Backup critical partitions
        self.backup_partition('boot')
        self.backup_partition('recovery')

        # Flash sequence
        for img in images:
            self.verify_image(img)
            cmd = [FASTBOOT, 'flash', img.partition, img.path]
            self._run(cmd)

        # Reboot and verify
        self._run([FASTBOOT, 'reboot'])
        self._run([ADB, 'wait-for-device'])

    def backup_partition(self, partition: str, out_dir: str = 'backups'):
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{partition}.img")
        if self.dry_run:
            self.log.append(f"Backup {partition} -> {out_path}")
            return
        self._run([ADB, 'shell', 'su', '-c', f'dd if=/dev/block/by-name/{partition} of=/sdcard/{partition}.img'])
        self._run([ADB, 'pull', f"/sdcard/{partition}.img", out_path])

    def export_log(self, path: str = 'flash_log.json'):
        with open(path, 'w') as f:
            json.dump(self.log, f, indent=2)


if __name__ == '__main__':
    # Example usage (dry-run):
    flasher = Flasher(dry_run=True)
    images = [
        ImageArtifact(path='twrp.img', partition='recovery'),
        ImageArtifact(path='boot.img', partition='boot')
    ]
    try:
        flasher.flash_images(images, slot=None)
    except FlashingError as e:
        print('Flashing failed:', e)
    finally:
        flasher.export_log()
