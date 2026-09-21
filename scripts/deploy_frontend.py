#!/usr/bin/env python3
"""
Dify Frontend Deploy Script
Automates: Slim Packaging (excluding cache) -> Upload via SFTP -> Extract -> Restart Service
"""
import os
import sys
import time
import argparse
import subprocess
import paramiko

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "web")
TAR_FILE = os.path.join(BASE_DIR, "dify-web-build.tar.gz")
SSH_FILE = os.path.join(BASE_DIR, ".ssh")

# Default SSH Configuration
HOST = "129.204.130.206"
PORT = 8443
USER = "root"
PASS = ""
REMOTE_DIR = "/www/wwwroot/dify/web"

if os.path.exists(SSH_FILE):
    with open(SSH_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
        if len(lines) >= 3:
            HOST, USER, PASS = lines[0], lines[1], lines[2]

def run_cmd(cmd, cwd=None):
    print(f">> Executing: {cmd}")
    res = subprocess.run(cmd, shell=True, cwd=cwd)
    if res.returncode != 0:
        print(f"Error: command failed with code {res.returncode}")
        sys.exit(res.returncode)

def pack_slim():
    print("\n--- 1. Packaging .next (excluding cache) ---")
    tar_cmd = f"tar -czf dify-web-build.tar.gz -C web --exclude='.next/cache' .next"
    run_cmd(tar_cmd, cwd=BASE_DIR)
    size_mb = os.path.getsize(TAR_FILE) / (1024 * 1024)
    print(f"Slim package created successfully: {TAR_FILE} ({size_mb:.2f} MB)")

def deploy(port=PORT):
    print(f"\n--- 2. Connecting to {HOST}:{port} ---")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=port, username=USER, password=PASS, timeout=15)
    print("SSH connected!")

    sftp = client.open_sftp()
    remote_tar = f"{REMOTE_DIR}/dify-web-build.tar.gz"
    client.exec_command(f"mkdir -p {REMOTE_DIR}")

    file_size = os.path.getsize(TAR_FILE)
    print(f"\n--- 3. Uploading ({file_size / (1024*1024):.2f} MB) via SFTP ---")
    start_time = time.time()
    last_print = [start_time]

    def progress(transferred, total):
        now = time.time()
        if now - last_print[0] >= 1.0 or transferred == total:
            rate = (transferred / (1024 * 1024)) / (now - start_time) if now > start_time else 0
            print(f"Upload: {transferred / (1024*1024):.1f}MB / {total / (1024*1024):.1f}MB ({(transferred/total)*100:.1f}%) - {rate:.2f} MB/s", flush=True)
            last_print[0] = now

    sftp.put(TAR_FILE, remote_tar, callback=progress)
    sftp.close()
    print(f"Uploaded in {time.time() - start_time:.1f}s!")

    print("\n--- 4. Extracting and verifying on server ---")
    extract_cmd = f"cd {REMOTE_DIR} && tar -xzf dify-web-build.tar.gz && rm -f dify-web-build.tar.gz && ls -la .next/BUILD_ID && cat .next/BUILD_ID"
    _, stdout, stderr = client.exec_command(extract_cmd)
    out = stdout.read().decode('utf-8', errors='ignore')
    err = stderr.read().decode('utf-8', errors='ignore')
    print("Verification result:\n" + out)
    if stderr.channel.recv_exit_status() != 0:
        print("Extract error:", err)

    print("\n--- 5. Reloading service ---")
    reload_cmd = "pm2 reload dify-web || pm2 restart dify-web || systemctl restart dify-web || true"
    _, stdout, _ = client.exec_command(reload_cmd)
    print(stdout.read().decode('utf-8', errors='ignore'))

    client.close()
    print("Deployment completed successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dify Frontend Deploy Tool")
    parser.add_argument("--build", action="store_true", help="Run pnpm build before deploy")
    parser.add_argument("--port", type=int, default=PORT, help=f"SSH port (default {PORT})")
    args = parser.parse_args()

    if args.build:
        print("\n--- Running pnpm build in web ---")
        run_cmd("pnpm build", cwd=WEB_DIR)

    pack_slim()
    deploy(port=args.port)
