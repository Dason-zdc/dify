---
name: dify-deploy-frontend
description: 当用户提出 Dify 前端构建、精简打包、部署到远程服务器、更新前端服务、重启 Web 容器或 PM2，以及分支开发与代码推送到个人 GitHub 仓库时调用。包含完整的生产环境配置检查、排除 cache 的高效打包、跨网络端口穿透上传、解压部署、服务重启与 Git 特性分支工作流。
---

# Dify 前端构建、精简打包与部署更新规范

本 Skill 规范了 Dify Web 前端的生产构建、极致瘦身打包、跨网络环境上传、服务器端部署服务更新，以及代码在个人 GitHub 仓库上的**特性分支开发与推送工作流**。

---

## 核心流程总览

```text
在 custom 分支改动代码 -> 生产构建 (pnpm build) -> 精简打包 (排除 cache) -> SFTP/SCP 上传 -> 服务端解压 -> 服务重启与验证 -> 推送到个人 GitHub (custom)
```

---

## 步骤一：环境与配置文件检查

1. **环境依赖**：
   - Node.js: `^24.20.0`（如 `24.21.0`）
   - pnpm: `>= 10.33`（如 `10.34.5` 或 Dify 声明的 `12.4.2`）
2. **生产配置文件**：`web/.env.local`
   ```dotenv
   NEXT_PUBLIC_DEPLOY_ENV=PRODUCTION
   NEXT_PUBLIC_BASE_PATH=
   CONSOLE_API_URL=http://<SERVER_IP>:5001
   NEXT_PUBLIC_API_PREFIX=http://<SERVER_IP>:5001/console/api
   NEXT_PUBLIC_PUBLIC_API_PREFIX=http://<SERVER_IP>:5001/api
   NEXT_PUBLIC_COOKIE_DOMAIN=
   NEXT_PUBLIC_SOCKET_URL=ws://<SERVER_IP>:5001
   NEXT_PUBLIC_MARKETPLACE_API_PREFIX=https://marketplace.dify.ai/api/v1
   NEXT_PUBLIC_MARKETPLACE_URL_PREFIX=https://marketplace.dify.ai
   NEXT_TELEMETRY_DISABLED=1
   ```

---

## 步骤二：生产构建

在项目根目录或 `web` 目录下执行构建：

```bash
# 在 web 目录下执行
cd web
pnpm build
```

- 确保构建输出结果 Exit code 为 `0`。
- 构建完成后，产物输出在 `web/.next/`。

---

## 步骤三：精简打包（必须排除 cache！）

> [!IMPORTANT]
> **切勿整包打包 `web/.next`！**
> `.next/cache` 是本地编译构建缓存，体积超过 2GB，生产运行**完全不需要**。
> 排除 `cache` 后，压缩包体积将从 **1.7 GB 锐减至约 100 MB**，传输提速 15~20 倍！

### 打包命令（排除 cache）：

```bash
# 在 dify 根目录下执行
tar -czf dify-web-build.tar.gz -C web --exclude='.next/cache' .next
```

---

## 步骤四：上传至远程服务器

### 网络与端口注意事项：
- 如果在**企业办公内网/受限局域网**环境下，出站通常封禁了 22 端口，但放行 `8443`、`8080`、`443` 等 Web 端口。
- 建议服务器端让 `sshd` 额外监听 `8443` 端口并在云安全组放行 `TCP:8443`：
  ```bash
  # 服务器端配置（已配置）：
  echo "Port 8443" >> /etc/ssh/sshd_config
  systemctl restart sshd
  ```

### 传输方式：

- **方式 A：使用内置自动化脚本（支持断点与速度展示）**
  ```bash
  python scripts/deploy_frontend.py
  ```
- **方式 B：原生 SCP 命令**
  ```bash
  scp -P 8443 dify-web-build.tar.gz root@<SERVER_IP>:/www/wwwroot/dify/web/
  ```

---

## 步骤五：服务器端解压与文件覆盖

登录服务器或通过 SSH 远程执行：

```bash
cd /www/wwwroot/dify/web/

# 1. 解压覆盖 .next
tar -xzf dify-web-build.tar.gz

# 2. 及时删除压缩包节省磁盘空间
rm -f dify-web-build.tar.gz

# 3. 验证部署产物
ls -la .next/BUILD_ID
cat .next/BUILD_ID
```

---

## 步骤六：更新并重启前端服务

根据服务器上的部署形态执行对应的重启命令：

### 1. PM2 部署模式
```bash
# 检查应用状态
pm2 list

# 平滑重启 / 重载应用
pm2 reload dify-web || pm2 restart dify-web
```

### 2. Docker Compose 部署模式
```bash
cd /www/wwwroot/dify/docker
docker compose restart web
```

### 3. Systemd 服务模式
```bash
systemctl restart dify-web
systemctl status dify-web
```

---

## 步骤七：专属定制分支（custom）日常提交与官方变基同步规范

为了避免多分支维护带来的冲突与心智负担，项目采用**单一专属定制分支（`custom`）**长期维护，日常提交与线上部署均基于该分支。

### 1. 远端架构说明
- **`origin`（个人 Fork 仓库）**：`git@github.com:Dason-zdc/dify.git`（具备读写权限，**所有修改与定制均推送到 origin/custom**）
- **`upstream`（官方开源仓库）**：`https://github.com/langgenius/dify.git`（官方源，只读，用于保持基础核心与最新发布同步）

### 2. 日常开发极简提交（单分支直接提交）

无需切分支，在 `custom` 分支直接修改代码：

```bash
# 1. 查看改动状态
git status

# 2. 暂存并提交代码
git add .
git commit -m "feat/fix: 简要描述你的改动"

# 3. 直接推送到你的个人仓库
git push
```

### 3. 同步官方 upstream 最新更新（变基 Rebase 规范）

当官方主干更新后，如果提示“落后 X 个提交”，按照以下标准流程执行**对齐变基（Rebase）**，保持提交历史干净且完全线性：

```bash
# 1. 拉取官方 upstream 最新提交
git fetch upstream main

# 2. 将当前 custom 分支的改动重放嫁接到官方最新主干之上
git rebase upstream/main

# 【如遇冲突】
# 编辑冲突文件解决后：
# git add .
# git rebase --continue
# （若想撤销本次变基放弃重放：git rebase --abort）

# 3. 将变基后的最新状态安全强制推送到自己的 GitHub 仓库
git push origin custom --force-with-lease

# 4. 验证对比状态（输出应为：0  <你的领先提交数>）
git rev-list --left-right --count upstream/main...HEAD
```

> [!CAUTION]
> **安全防护提醒**：
> 本地 `.git/info/exclude` 中已强制配置忽略 `*.tar.gz`、`.ssh`、`scripts/.ssh`、`web/.env.local`。切勿将包含服务器凭证或环境私密信息的文件提交并推送到 GitHub 公开仓库！

---

## 配套自动化部署脚本

在 `scripts/deploy_frontend.py` 中封装了一键打包、上传、解压、重启服务的完整流水线，随时可一键执行：
```bash
python scripts/deploy_frontend.py
```
