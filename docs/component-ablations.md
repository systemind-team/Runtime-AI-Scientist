# R2+C / R2+V：开始第一次测试

本教程不限定具体 host、task 或模型。命令面向 Linux/Bash；离线检查不调用模型，正式运行和评分会使用你配置的模型服务。

## 1. 两个条件的区别

| 条件 | SharedNet 通信 | 运行时选择 | 向执行 agent 提供契约 | verifier advisory |
|---|---|---|---|---|
| R2 | ✓ | ✓ | — | — |
| R2+C | ✓ | ✓ | ✓ | — |
| R2+V | ✓ | ✓ | — | ✓ |
| R3 | ✓ | ✓ | ✓ | ✓ |

**R2+C** 复用 R3 的 work contract 构建与注入逻辑，不运行 verifier；路由及无 verifier 时的错误处理沿用 R2。

**R2+V** 不向执行 agent 注入契约。在调用前冻结与 R3 相同的证据标准，保存为 `verification_spec`；调用后复用现有 verifier 检查产物，将结果作为 advisory 提供给下一位 agent。因此“只加 verifier”去掉的是执行 agent 收到的契约，不是验证所需的评估标准。

verifier 是 `src/rac_ai_scientist/policy.py::verify_result` 中的结构化证据检查，不是新增 LLM judge 调用。它与外部 benchmark 评分不同。R2+V 与 R3 一样，验证结论本身不会强制停止、重试、重路由或回滚；带有验证结果的非终止性调用错误也保留产物和 host 状态。终止性 provider 错误、预算/hop 上限及 host 完成仍可结束 episode。解释消融结果时，应考虑这套 advisory 错误处理语义。

CLI 接受 `R2+C` / `R2+V`，也接受别名 `R2_C` / `R2_V`；序列化记录可能使用下划线。它们不是 R4/R5，也不是 R3 之上的累积等级。原有 N0–R3 行为保持不变。

## 2. 获取代码并检查

需要 Python 3.10+、Git。正式运行还需支持 BuildKit named contexts 的 Docker Compose v2，以及对模型服务和 SharedNet 的网络访问。

```bash
git clone https://github.com/FORLEMON/RAC-AI_Scientist.git
cd RAC-AI_Scientist
# 若 main 尚未合并此改动，使用发布分支：
git switch feat/r2-component-ablations-public
export REPO="$(pwd)"
export PYTHONPATH="$REPO/src"
python3 -m unittest discover -s tests -v
python3 scripts/check_secrets.py
python3 -m rac_ai_scientist.cli run-one --help
git rev-parse HEAD
```

确认测试通过，CLI help 包含两个新条件，记录代码 SHA。`tests/test_component_ablations.py` 覆盖功能矩阵、原条件兼容性、契约可见性、调用前冻结标准、SharedNet advisory 和错误处理。

这里直接从源码运行 CLI，不要求宿主机创建虚拟环境。host 依赖在各自 Docker 镜像内安装。安装为命令行工具的方法见 [公共运行手册](runbook.md)。

## 3. 选择输入并构建镜像

把下列占位符替换为自己的选择。`HOST` 是 CLI host ID，`SERVICE` 是对应的 Compose service；两者可能不同，支持的映射见 [Supported scope](runbook.md#supported-scope)。`TASK` 应与 benchmark 的任务目录名一致。

```bash
export HOST='<host-id>'
export SERVICE='<compose-service>'
export TASK='<benchmark-task-id>'
export CONDITION='R2+C'       # 或 R2+V

python3 scripts/bootstrap.py --only "$HOST" --only researchclawbench
python3 -m rac_ai_scientist.cli verify-upstreams \
  --only "$HOST" --only researchclawbench

# 稳定镜像名让不同 Compose project 复用同一次构建。
mkdir -p "$REPO/runs"
export HOST_IMAGE="rac-components-$SERVICE:local"
export JUDGE_IMAGE='rac-components-scorer:local'
cat > "$REPO/runs/component-images.yaml" <<YAML
services:
  $SERVICE:
    image: $HOST_IMAGE
  scorer:
    image: $JUDGE_IMAGE
YAML
export COMPOSE_FILE="$REPO/compose.yaml:$REPO/runs/component-images.yaml"
docker compose build "$SERVICE" scorer
```

必须确认 build 退出码为 0；旧镜像仍存在不代表本次构建成功。不要修改固定 upstream 或 benchmark。如果其他实验在使用这些标签，换成自己的唯一标签。共享机器按可用资源设置 CPU、内存和线程限制，首次先串行试一格。

## 4. 配置模型和独立 judge

```bash
cp .env.example .env
chmod 600 .env
vim .env
```

填写 `AGENT_API_BASE`、`AGENT_API_KEY`、`AGENT_MODEL_NAME` 及独立的 `JUDGE_*` 配置。这份指南使用仓库的 API 接入方式，不要求特定模型或服务器私有订阅网关。Azure judge 使用 endpoint 根地址和部署名，保持 `JUDGE_MAX_WORKERS=1`；其余见 `.env.example` 和 [评分说明](runbook.md#7-score-the-episode)。

比较条件时固定模型、推理设置、输入、工具权限、预算和 judge 设置。全局 `SHAREDNET_ROOM_ID`、`SHAREDNET_INVITE` 留空，每格在自己的 prepared task 配置房间。不要打印或提交填好凭据的 `.env`，也不要公开完整 `docker compose config` 输出。

## 5. 准备隔离输入和新房间

```bash
export EPISODE="ablation-$(date -u +%y%m%d%H%M%S)-$(python3 -c 'import secrets; print(secrets.token_hex(4))')"
export PREPARED_TASK="$REPO/prepared_tasks/$EPISODE"
export CELL_RUN_ROOT="$REPO/runs/cells/$EPISODE"
export COMPOSE_PROJECT_NAME="rac-$EPISODE"
mkdir -p "$CELL_RUN_ROOT"

python3 -m rac_ai_scientist.cli prepare-task \
  --task-dir "$REPO/upstreams/researchclawbench/tasks/$TASK" \
  --output "$PREPARED_TASK"
python3 -m rac_ai_scientist.cli check-workspace "$PREPARED_TASK"
vim "$PREPARED_TASK/.env"
chmod 600 "$PREPARED_TASK/.env"
```

用自己的 SharedNet UI 或 CLI 创建一个**新 Room**，在最后这个文件填入它的配置：

```dotenv
SHAREDNET_ROOM_ID=rom_example
SHAREDNET_INVITE='ROOM=rom_example TOKEN=rit_REDACTED BASE=https://www.sharednet.ai'
SHAREDNET_BASE_URL=https://www.sharednet.ai
```

这些是占位符。使用完整 invite，且 Room ID 必须匹配。每次尝试都需要新的 episode、输入目录、运行目录和 Room，包括失败重试。

不要向执行 host 挂载含 `target_study` 的原始任务目录；`prepare-task` 生成目标隔离的输入。仅外部 scorer 可以读取 benchmark 目标材料。

## 6. 零模型调用的预检查

```bash
docker compose run --rm --no-deps "$SERVICE" doctor-host --host "$HOST"
docker compose run --rm --no-deps "$SERVICE" check-workspace /input/task
docker compose run --rm --no-deps "$SERVICE" run-one --help
```

要求全部通过，且镜像内 CLI 支持新条件。这不能证明模型账户有访问权限或配额，首次正式运行应作为接入测试。命令均在仓库根目录和同一组导出变量下执行；换 shell/tmux 后恢复变量，尤其是 `COMPOSE_FILE` 和本格路径。

## 7. 设置预算并启动

以下数字仅说明参数位置，**不是所有 host/task/model 的推荐预算**。按自己的校准结果填写正数；比较不同条件时保持预算匹配。

```bash
export MAX_INPUT=1400000 MAX_OUTPUT=125000 MAX_CALLS=100000
export MAX_HOPS=14 MAX_SECONDS=5400 MAX_COST_USD=70
export RAC_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$HOST_IMAGE")"
export HOST_CONTAINER="rac-$EPISODE-host"

# 从这里开始调用模型。保留失败日志和退出码。
set +e
timeout --signal=TERM --kill-after=30s "${MAX_SECONDS}s" \
  docker compose run --name "$HOST_CONTAINER" --no-deps "$SERVICE" run-one \
  --host "$HOST" --condition "$CONDITION" \
  --task-dir /input/task --sharednet-env-file /input/task/.env \
  --run-root /runs --episode-id "$EPISODE" --seed 0 \
  --max-cost-usd "$MAX_COST_USD" \
  --max-input-tokens "$MAX_INPUT" --max-output-tokens "$MAX_OUTPUT" \
  --max-agent-calls "$MAX_CALLS" --max-hops "$MAX_HOPS" \
  --max-wall-seconds "$MAX_SECONDS" > "$CELL_RUN_ROOT/host.log" 2>&1
HOST_EXIT=$?
printf '%s\n' "$HOST_EXIT" > "$CELL_RUN_ROOT/host-exit-code.txt"
if [ "$HOST_EXIT" -eq 124 ] || [ "$HOST_EXIT" -eq 137 ]; then
  docker stop -t 10 "$HOST_CONTAINER"
fi
docker inspect --format '{{json .State}}' "$HOST_CONTAINER" \
  > "$CELL_RUN_ROOT/container-state.json"
# 仅删除本格已停止容器；不删除结果，不强制移除运行中的容器。
docker rm "$HOST_CONTAINER"
```

`--max-agent-calls` 统计报告的 agent 调用，不必然等于底层 HTTP 请求数。输入 token 通常包含已报告的缓存输入，失败请求可能有未知用量。USD 限额依赖有效费用归因，显示 0 不等于免费。token 限额在调用之间检查时，单次调用可能超出剩余预算。

外层 `timeout` 防止阻塞调用无限等待；超时后停止的只是本格命名容器。评分时间不计入 host 预算。长期运行可在 tmux 内执行本节，先恢复环境变量。

## 8. 看日志、核验条件、评分

在另一终端恢复 `CELL_RUN_ROOT` 后查看：

```bash
tail -n 80 -F "$CELL_RUN_ROOT/host.log"
docker ps --format '{{.Names}} {{.Status}}'
docker stats --no-stream
```

日志短暂安静不等于卡死。结束后检查 `$CELL_RUN_ROOT/$EPISODE/episode.json` 和 `coordination.jsonl`：

- `execution_mode` 应为 `sharednet_rac_episode_runner`。
- R2+C：`rac_features.work_contracts=true`、`verifier=false`；可执行 decision 带 `contract`，没有验证 verdict。
- R2+V：`work_contracts=false`、`verifier=true`；可执行 decision 的 `contract=null`、`verification_spec` 非空；符合条件的调用后产生 advisory。终止性 provider 错误可能在 verdict 前结束。
- ledger 保留 checkpoint、decision、invocation 和 evaluation；SharedNet 中有 typed request/result，以及 R2+V 的 `work.verification`。

有非空 `workspace/report/report.md` 时可按预定规则独立评分，即使 host 非零退出也应保留产物。缺失报告记为未评分/null，不能伪造为 0。

```bash
export SCORER_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$JUDGE_IMAGE")"
docker compose run --rm --no-deps scorer score-episode \
  --episode-dir "/runs/$EPISODE" --benchmark /opt/benchmark \
  > "$CELL_RUN_ROOT/score.log" 2>&1
```

要求评分退出码为 0，`score.json` 无错误且条目完整。judge HTTP/解析失败与合法零分不同。完整前置条件见 [公共运行手册](runbook.md#7-score-the-episode)。重复评分需保留 `scores/` 中每次尝试并固定聚合规则；`score.json` 不会自动成为多次评分中位数。

## 9. 换条件和分享结果

修改 `CONDITION`，**从步骤 5 生成新 episode 和新房间**，再检查、运行、评分。不要覆盖已有结果。CLI 不识别条件时检查代码 SHA 和镜像重建；房间失败时检查本格 `.env` 和 invite；请求超时/OOM 后保留日志和容器状态，再新建重试。

复现记录至少包含代码 SHA、upstream revisions、镜像 ID、host/task/seed/condition、模型与推理设置、预算、结束原因、token/call/hop 用量及评分规则。不要分享凭据、invite 或 prepared task `.env`。归档时排除每个 workspace 的 `.conda_env/`；它是运行环境，不是实验产物。本教程不包含实验分数和服务器私有配置。
