# NUS 官方依据与实时发现

核对日期：2026-10-12（Asia/Singapore）。以下为网页当日观察，不保证未来配置。

## 主要依据

[Introductory Guide for New HPC Users](https://nusit.nus.edu.sg/hpc/introductory-guide-for-new-hpc-users/)：通过浏览器展开全部章节读取；网页抓取接口返回 403，正文可经浏览器访问。

- 指南确认 NUS-ID 认证和 PBS。长任务需提交队列；普通交互及 `&` 后台计算受 30 分钟 CPU 限制，不能将其误解为所有 PBS 交互作业的 walltime。
- 主机表当前列出 atlas9、vanda、hopper（域名均为 `.nus.edu.sg`）。硬件、开放资格、费用和队列需现场核验；不默认仍能使用旧资料中的 atlas8。
- 指南给出全局 home `/home/svu/$USERID`、20 GB、最长 10 天 snapshot；Atlas 的 `/hpctmp` 500 GB、无备份、超过 60 天的文件会清理。这些数字不能泛化到 Vanda/Hopper/Cloud，不作为持久归档保证。
- 传输使用 SFTP/SCP；可用 `hpc s` 检查配额。PBS 内部手册为 [bobcat PBS guide](https://bobcat.nus.edu.sg/hpc/HPC/pbs/index.html)，仅校内访问；现场可用 `hpc pbs help`。
- 指南链接的旧 workspace 页面在核对日重定向后返回 404；尚未取得详细清理算法或自动续期政策，不推断按 atime/mtime 清理，不承诺 `touch` 有效。
- 未发现该公开指南定义 HPC 账号自动续期 API、统一年度续期周期或允许用户自行延长运行中作业的规则。应从当前账号门户、项目批准信或 HPC 支持取得证据。

其他官方来源：

- [nVPN](https://nusit.nus.edu.sg/services/wifi_internet/nvpn/)：校外访问内部受限资源需 NUS VPN，配置文档在 A.S.K.。VPN 认证与 SSH 是不同阶段；勿用旧教程的 HTTP VPN URL。
- [Remote Working](https://nusit.nus.edu.sg/itcare/remote-working/)：nVPN 需要 2FA；不推断每次 SSH 都用相同 MFA 机制。
- [NUS HPC customised tools](https://nusit.nus.edu.sg/services/hpc-newsletter/handy-tools-customised-for-hpc-parallel-computing/)（2019）：`gstat`、`qlist`、`hpc space`，以主机上可用命令为准。
- [OpenPBS qstat 源手册](https://github.com/openpbs/openpbs/blob/master/doc/man1/qstat.1B) 与 [依赖示例](https://community.openpbs.org/t/new-accounting-records-to-track-the-jobs-lifecycle/1794)：通用 PBS 参考，不构成 NUS 站点许可。命令参数仍需匹配服务器版本。

## 登录后只读发现

逐项执行，允许个别命令不存在，不把单个缺失命令当成系统故障：

```sh
hostname -f
id -un
command -v qsub qstat qdel hpc
hpc pbs help
qstat -Qf
hpc space
df -h
```

模块命令可能仅在 login shell 初始化后出现；按站点文档检查 `module avail`。GPU 不在登录节点运行 `nvidia-smi` 来判断队列硬件，用队列/节点文档并在获准的 GPU PBS 作业中验证。

只保存非敏感配置：SSH alias、实际集群/PBS server、队列限制、资源语法、模块、工作/归档路径、保留策略来源和核对日期。未知值保留 null，不能填入貌似合理的默认值。

## 2026-10-12 Hopper 实测补充

以下来自这次已完成测试的主机帮助、队列配置及 PBS 返回值；是有日期的运行证据，不推广为所有集群永久规则。

- 普通远程 SSH 命令找不到 `qsub/qstat`，但 `bash -lc` 加载登录环境后可用。`hpc pbs help` 同时指示命令不可用时先 `module load pbs`。因此命令缺失要先检查环境，不能直接判断无 PBS 或改用 Slurm。
- Hopper 样例要求 `#PBS -P Project-Name` 和 `select=1:ngpus=1`。普通路由队列 `auto` 将 1 GPU 的测试送入 `small`；后者为 `from_route_only=True` 且最少 1 GPU。应通过路由队列提交，不直接向 small 投递，不为了“CPU 小任务”请求不符合该站点的零 GPU 资源。
- 本次 1 GPU 请求由站点展开为 12 CPU、225 GB 内存。帮助也说明按 GPU 自动分配。模板保留 `ngpus`，不要把这个观测比例写成客户端强制值；资源/额度说明可引用实测值并注明日期。
- `hpc project` 需要另外登录预算服务，但已知项目的 `qsub -P` 成功提交并结束，过程中未运行 `amgr login/sshlogin`。预算服务会话不是已知项目提交的必经步骤。项目余额/到期仍未知，不能从调度接受推断。
- 本次账号的 `hpc space` 报告 home 40 GB、`/scratch` 1 TB，进一步说明入门页的 Atlas 配额不能泛化。此数值只属于该次账号查询，不作为任何用户默认值。
- 1 分钟 walltime 的简单求和测试实际运行 2 秒，PBS `F`、`Exit_status=0`、应用 `COMPLETE`，输出 `5000050000`，并成功读回结果。只验证了认证复用、项目提交、调度和结果读取；未验证 GPU 数值计算、checkpoint、自动续期、Linux 无头服务或无人值守重认证。

可复用资料不含该次个人用户名/项目作为默认值；每个项目在自己的私有清单里保存配置。
