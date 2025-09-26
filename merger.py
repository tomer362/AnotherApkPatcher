# merger.py
"""Functions for merging APKs using APKEditor."""

import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Optional
import config


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration"""
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=log_level, format=log_format)


def run_command(cmd: list, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    """Run a shell command and return the result"""
    logging.info(f"Running command: {' '.join(cmd)}")
    try:
        process = subprocess.run(
            cmd,
            cwd=cwd,
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


def build_apkeditor() -> bool:
    """Build APKEditor from source (stub implementation)"""
    # Placeholder for building APKEditor from source
    # This would involve running Gradle commands in the libs/APKEditor directory
    logging.info("Building APKEditor from source is not implemented in this stub.")
    # Example logic (uncomment and adapt if needed):
    # try:
    #     apkeditor_dir = Path("libs/APKEditor")
    #     if not apkeditor_dir.exists():
    #         logging.error("APKEditor submodule not found.")
    #         return False
    #     gradlew = apkeditor_dir / ("gradlew.bat" if sys.platform == "win32" else "gradlew")
    #     if not gradlew.exists():
    #         logging.error("Gradle wrapper not found.")
    #         return False
    #     if sys.platform != "win32":
    #         import stat
    #         gradlew.chmod(gradlew.stat().st_mode | stat.S_IEXEC)
    #     run_command([str(gradlew), "build"], cwd=str(apkeditor_dir))
    #     # Find and copy the built JAR...
    #     logging.info("APKEditor built successfully.")
    #     return True
    # except Exception as e:
    #     logging.error(f"Failed to build APKEditor: {e}")
    return False # Indicate build not performed


def merge_apks(
    base_apk: str,
    unsigned_apks: List[str],
    output_apk: str,
    apkeditor_jar: str = str(config.APKEDITOR_JAR_DEFAULT),
    verbose: bool = False
) -> bool:
    """
    Merge base APK with multiple unsigned APKs using APKEditor's merge feature

    Args:
        base_apk: Path to the base APK
        unsigned_apks: List of paths to unsigned APKs to merge
        output_apk: Path for the output merged APK
        apkeditor_jar: Path to APKEditor JAR file
        verbose: Enable verbose logging

    Returns:
        True if merge successful, False otherwise
    """
    setup_logging(verbose)

    # Check if APKEditor JAR exists
    jar_path = Path(apkeditor_jar)
    if not jar_path.exists():
        logging.warning(f"APKEditor JAR not found at {jar_path}")
        logging.info("Attempting to build APKEditor...")
        if not build_apkeditor():
            logging.error("Failed to build APKEditor")
            return False
        # Re-check if build created the JAR
        if not jar_path.exists():
             logging.error("APKEditor JAR still not found after attempted build.")
             return False
        logging.info("APKEditor JAR located after build attempt.")

    # Verify base APK exists
    base_apk_path = Path(base_apk)
    if not base_apk_path.exists():
        logging.error(f"Base APK not found: {base_apk}")
        return False

    # Verify all unsigned APKs exist
    unsigned_apk_paths = []
    for unsigned_apk in unsigned_apks:
        unsigned_apk_path = Path(unsigned_apk)
        if not unsigned_apk_path.exists():
            logging.error(f"Unsigned APK not found: {unsigned_apk}")
            return False
        unsigned_apk_paths.append(str(unsigned_apk_path))

    if not unsigned_apk_paths:
        logging.error("No unsigned APKs provided for merging")
        return False

    try:
        # Run APKEditor merge command
        # java -jar APKEditor.jar merge -i base.apk -u unsigned1.apk -u unsigned2.apk -o output.apk
        merge_cmd = [
            config.JAVA_BINARY_PATH, "-jar", str(jar_path),
            "merge",
            "-i", str(base_apk_path),
            "-o", str(output_apk)
        ]

        # Add all unsigned APKs
        for unsigned_apk in unsigned_apk_paths:
            merge_cmd.extend(["-u", unsigned_apk])

        run_command(merge_cmd)
        logging.info(f"APKs merged successfully to {output_apk}")
        return True

    except Exception as e:
        logging.error(f"Failed to merge APKs: {e}")
        return False


def main():
    """Main function for command-line usage"""
    import argparse

    parser = argparse.ArgumentParser(description="APK Merger using APKEditor")
    parser.add_argument("base_apk", help="Path to the base APK")
    parser.add_argument("unsigned_apk", nargs="+", help="Paths to unsigned APKs to merge")
    parser.add_argument("-o", "--output", default=config.DEFAULT_MERGED_APK_NAME,
                       help=f"Output APK path (default: {config.DEFAULT_MERGED_APK_NAME})")
    parser.add_argument("--apkeditor-jar", default=str(config.APKEDITOR_JAR_DEFAULT),
                       help=f"Path to APKEditor JAR file (default: {config.APKEDITOR_JAR_DEFAULT})")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--build", action="store_true",
                       help="Build APKEditor from source")

    args = parser.parse_args()

    # Setup logging based on verbosity
    setup_logging(args.verbose)

    # Build APKEditor if requested
    if args.build:
        if not build_apkeditor():
            return 1

    # Perform merge
    success = merge_apks(
        base_apk=args.base_apk,
        unsigned_apks=args.unsigned_apk,
        output_apk=args.output,
        apkeditor_jar=args.apkeditor_jar,
        verbose=args.verbose
    )

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
