"""Utility functions for APK processing with external tools"""

import logging
import subprocess
import shutil
import json
import sys
from pathlib import Path
from typing import List, Dict, Optional
import config


def run_command(cmd: list, cwd: Optional[str] = None, input_data: Optional[str] = None) -> subprocess.CompletedProcess:
    """Run a shell command and return the result"""
    logging.info(f"Running command: {' '.join(cmd)}")
    try:
        process = subprocess.run(
            cmd,
            cwd=cwd,
            input=input_data,
            text=True,
            capture_output=True,
            check=True
        )
        logging.debug(f"Command output: {process.stdout}")
        return process
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed with return code {e.returncode}")
        logging.error(f"Error output: {e.stderr}")
        raise


def decompile_apk(apk_path: str, output_dir: Path, apktool_path: Path) -> None:
    """Decompile the APK using apktool"""
    logging.info(f"Decompiling APK: {apk_path}")
    cmd = [config.JAVA_BINARY_PATH, "-jar", str(apktool_path), config.APKTOOL_DECODE_CMD, apk_path, "-o", str(output_dir)]
    run_command(cmd)


def compile_apk(decompiled_dir: Path, output_apk: Path, apktool_path: Path) -> None:
    """Compile the modified sources back to APK"""
    logging.info(f"Compiling APK to: {output_apk}")
    cmd = [config.JAVA_BINARY_PATH, "-jar", str(apktool_path), config.APKTOOL_BUILD_CMD, str(decompiled_dir), "-o", str(output_apk)]
    run_command(cmd)


def align_apk(input_apk: Path, output_apk: Path, zipalign_path: Path) -> None:
    """Align the APK using zipalign"""
    logging.info(f"Aligning APK: {input_apk}")
    cmd = [str(zipalign_path)] + config.ZIPALIGN_FLAGS + [str(input_apk), str(output_apk)]
    run_command(cmd)


def generate_key(keystore_path: Path, alias: str, password: str, keytool_path: Path) -> None:
    """Generate a new keystore with keytool"""
    logging.info(f"Generating new keystore: {keystore_path}")

    # Prepare input for keytool (password twice)
    keytool_input = f"{password}\n{password}\n"

    cmd = [
        str(keytool_path),
        "-genkey",
        "-v",
        "-keystore", str(keystore_path),
        "-alias", alias,
        "-keyalg", config.KEY_ALGORITHM,
        "-keysize", config.KEY_SIZE,
        "-validity", config.KEYSTORE_VALIDITY,
        "-storepass", password,
        "-keypass", password,
        "-dname", config.KEY_DNAME
    ]

    run_command(cmd, input_data=keytool_input)


def sign_apk(apk_path: Path, keystore_path: Path, alias: str, password: str, apksigner_path: Path) -> None:
    """Sign the APK using apksigner"""
    
    logging.info(f"Signing APK: {apk_path}")
    cmd = [
        str(apksigner_path),
        config.APKSIGNER_SIGN_CMD,
        "--ks", str(keystore_path),
        "--ks-key-alias", alias,
        "--ks-pass", f"pass:{password}",
        "--key-pass", f"pass:{password}",
        "--out", str(apk_path),
        str(apk_path)
    ]
    run_command(cmd)


def interactive_file_modification(decompiled_dir: Path) -> None:
    """Allow user to interactively modify files"""
    print(f"\nAPK decompiled to: {decompiled_dir}")
    print("You can now modify files in this directory.")
    input("Press Enter when you're done with modifications...")


def load_patches_from_json(patches_file: Path) -> List[Dict[str, str]]:
    """Load file patches from a JSON file"""
    try:
        with open(patches_file, 'r') as f:
            data = json.load(f)

        # Extract patches from the JSON data
        if 'patch' in data and isinstance(data['patch'], list):
            patches = []
            for item in data['patch']:
                if isinstance(item, dict) and 'src' in item and 'dest' in item:
                    patches.append({
                        'src': item['src'],
                        'dest': item['dest']
                    })
            return patches
        else:
            raise ValueError("JSON file must contain a 'patch' array of objects with 'src' and 'dest' keys")
    except Exception as e:
        logging.error(f"Failed to load patches from {patches_file}: {e}")
        raise


def apply_file_patches(decompiled_dir: Path, patches: List[Dict[str, str]]) -> None:
    """Apply file patches from source to destination paths"""
    logging.info(f"Applying {len(patches)} file patches...")

    for i, patch in enumerate(patches):
        if not isinstance(patch, dict) or 'src' not in patch or 'dest' not in patch:
            logging.warning(f"Skipping invalid patch at index {i}: {patch}")
            continue

        src_path = Path(patch['src'])
        dest_path = decompiled_dir / patch['dest']

        # Validate source file exists
        if not src_path.exists():
            logging.warning(f"Source file does not exist: {src_path}")
            continue

        # Create destination directory if needed
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        try:
            shutil.copy2(src_path, dest_path)
            logging.info(f"Copied {src_path} to {dest_path}")
        except Exception as e:
            logging.error(f"Failed to copy {src_path} to {dest_path}: {e}")


def install_apk_on_device(apk_path: str, device_serial: Optional[str] = None) -> bool:
    """Install APK on connected device(s)"""
    try:
        # Get connected devices
        result = run_command([config.ADB_CMD, config.ADB_DEVICES_CMD])
        lines = result.stdout.strip().split('\n')[1:]  # Skip header
        devices = []
        for line in lines:
            if line.strip() and not line.startswith('*') and '\t' in line:
                device_id = line.split('\t')[0]
                devices.append(device_id)

        if not devices:
            logging.error("No ADB devices connected")
            return False

        if device_serial:
            # Install on specific device
            if device_serial not in devices:
                logging.error(f"Device {device_serial} not found in connected devices: {devices}")
                return False

            logging.info(f"Installing APK on device {device_serial}...")
            cmd = [config.ADB_CMD, "-s", device_serial, config.ADB_INSTALL_CMD] + config.ADB_INSTALL_FLAGS + [apk_path]
            run_command(cmd)
            logging.info("APK installed successfully")
            return True
        elif len(devices) == 1:
            # Install on single device
            logging.info(f"Installing APK on device {devices[0]}...")
            cmd = [config.ADB_CMD, "-s", devices[0], config.ADB_INSTALL_CMD] + config.ADB_INSTALL_FLAGS + [apk_path]
            run_command(cmd)
            logging.info("APK installed successfully")
            return True
        else:
            # Multiple devices - show instructions
            print("\n" + "="*60)
            print("MULTIPLE DEVICES DETECTED")
            print("="*60)
            print("Connected devices:")
            for i, device in enumerate(devices, 1):
                print(f"  {i}. {device}")

            print("\nTo install on a specific device, run:")
            # Reconstruct the command with device serial
            cmd_parts = [sys.argv[0]] + sys.argv[1:] + ["--install-on-device", "<device_serial>"]
            print(f"  {' '.join(cmd_parts)}")
            print("="*60)
            return True

    except Exception as e:
        logging.error(f"Failed to install APK: {e}")
        return False
