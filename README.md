# NUS HPC Skill

An Agent Skill for using NUS IT HPC from macOS and headless Linux: secure authentication, PBS job preparation and management, monitoring, checkpoint continuation, and expiry handling.

面向 macOS 与无头 Linux 的 NUS HPC 一站式操作技能。社区维护，**非 NUS 官方项目**；使用资格、队列资源、收费和认证政策以 NUS IT 当前规定为准。

## 能做什么

- 复用 SSH 配置、已有凭据工具和有限期会话；区分 VPN、SSH、PBS 与预算服务认证。
- 准备环境与输入、生成 CPU/GPU PBS 脚本、跟踪任务和读取校验后的结果。
- 支持 Hopper 项目参数与站点自动 CPU/内存分配，兼顾 Atlas/Vanda 的不同配置。
- 指导有限 checkpoint 接续、到期提醒及归档，明确预算和停止条件。

Skill 是供代理使用的操作指南。附带工具只进行本地检查、只读连接预检和 PBS 文件生成；不会自行保存密码、提交计算或启用永久后台服务。任务提交、监控和恢复由代理按当前用户授权执行。

## 安装到 Codex

先克隆仓库，将 `skills/nus-hpc` 复制到本机技能目录。目标目录已有同名 skill 时，先检查和备份已有版本；下面的命令会拒绝覆盖。

```sh
git clone https://github.com/hooozen/nus-hpc-skill.git
cd nus-hpc-skill
skill_dest="${CODEX_HOME:-$HOME/.codex}/skills/nus-hpc"
if [ -e "$skill_dest" ]; then
    printf 'Skill already exists: %s\n' "$skill_dest"
else
    mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
    cp -R skills/nus-hpc "$skill_dest"
fi
```

在能够发现该 skill 的新会话中使用 `$nus-hpc`，例如：

> 使用 $nus-hpc，检查现有 NUS HPC 连接，然后用我指定的项目提交一个最长 1 分钟的测试任务，监控并验证结果。

其他支持 Agent Skills 的工具可将该目录安装到各自技能目录；本仓库的 Codex UI 元数据是可选适配文件。

## 环境与认证

本地辅助工具需要 Python 3.8+ 和 OpenSSH；远端脚本需要 Bash。网络/VPN、HPC 开通资格、队列和项目权限需在实际执行环境核验。

- **macOS**：优先复用用户终端建立的 SSH master，或已经配置并授权的 Keychain 登录 helper。
- **无头 Linux**：优先由用户在同机、同账号的 TTY 完成认证，后台使用私有 ControlMaster socket；桌面 Secret Service/密钥环不是默认前提。
- **密钥登录**：仅在站点允许时使用专用加密 key 与有限期 ssh-agent。
- **长期托管**：检查执行器的网络、认证、运行身份与绝对授权期限。机器注销、重启或 MFA 到期可能需要人工恢复。

完整流程见 [认证指南](skills/nus-hpc/references/authentication.md)。密码、OTP、私钥及 token 不应进入聊天、项目文件或日志。

## 辅助工具

以下命令从仓库根目录运行。

```sh
# 仅检查本地能力，不访问网络或凭据
python3 skills/nus-hpc/scripts/hpc.py doctor

# nus-hpc 是已配置并核对主机密钥的 SSH alias
python3 skills/nus-hpc/scripts/hpc.py probe --host nus-hpc
```

预检加载远端 Bash 登录环境，必要时尝试 `module load pbs`。返回 0 表示身份、PBS 命令和队列检查通过；2 表示本地工具/SSH/超时错误；3 表示 PBS 未就绪。预检不验证项目余额，也不代替真实计算验收。

Hopper 测试脚本生成示例，替换真实项目、唯一任务名和已确认的工作目录：

```sh
python3 skills/nus-hpc/scripts/hpc.py render \
  --profile hopper --project YOUR_PROJECT_ID --name smoke_unique \
  --ngpus 1 --walltime 00:01:00 \
  --workdir /absolute/verified/workdir \
  --command-file skills/nus-hpc/assets/smoke.sh --output smoke.pbs
```

生成后先审阅，再在指定工作目录提交。Hopper 普通队列的最小资源可能包括 1 GPU，即使测试程序仅进行 CPU 求和；纯 CPU 工作优先选择已获准的 CPU 队列。提交、异常恢复和结果读取见 [任务操作指南](skills/nus-hpc/references/operations.md)。

## 验证范围

2026-10-12 的 Hopper 实测已验证：安全会话复用、已知项目的 PBS 提交、排队/执行、退出码和结果读取。测试求和 `1..100000` 得到 `5000050000`，实际运行 2 秒，退出码 0。

本仓库还包含离线回归测试及 macOS/Ubuntu CI。无头 Linux 的实际 VPN/MFA、长期后台服务、GPU 数值计算、checkpoint 恢复及自动续期尚未完成现场验证。公开资料未证明统一的账号自动续期接口；该部分按当前正式流程、提醒和申请处理。

```sh
python3 skills/nus-hpc/scripts/test_hpc.py
```

测试不读取真实凭据、不连接 HPC、不消耗项目额度。贡献时请附可复现步骤和去敏后的错误信息；保持站点配置可核验，不将个人项目或主机认证配置作为默认值。

## 来源与许可

- [NUS HPC 入门指南](https://nusit.nus.edu.sg/hpc/introductory-guide-for-new-hpc-users/)
- [站点依据及有日期的实测说明](skills/nus-hpc/references/site-facts.md)
- [有限接续与续期策略](skills/nus-hpc/references/continuation.md)

本项目原创代码与说明采用 [MIT License](LICENSE)。外部链接资料由原作者维护，适用其各自条款。
