# 循序设备 Agent

Python 3.9+ 标准库工作进程；Java 核心服务拥有最终业务写入权。Agent 只注册、领取经过用户派发的命令、执行并报告事件。

```sh
python3 device-agent/agent.py --server http://127.0.0.1:8080 --workspace /absolute/research-workspace --name local-device --once
```

省略 `--once` 持续轮询。服务可要求环境变量 `XUNXU_DEVICE_SERVER_TOKEN`；认证凭据不打印。每设备凭据存于工作目录 `.xunxu-agent.json`，权限 0600。任务通过参数列表执行，禁止 shell 隐式解析，cwd 限制在指定工作目录内。命令本身具有本机用户权限，此目录检查不构成操作系统沙盒；仅派发可信研究代码。

API：`POST /api/devices/register {name,workspace}` 返回 `{device_id,device_token}`；`heartbeat`、`POST /api/jobs/claim` 携带两字段；领取返回 `{job:null}` 或 `{job:{id,run_id,argv,cwd,timeout_seconds}}`。`POST /api/runs/{id}/report` 还携带 `job_id,event_id,sequence,status,message,result`。事件依次为 running、returning、verifying、completed/failed；每步稳定事件 ID，网络重试幂等。

已领取任务不自动重新排队。Agent 重启发现未完成 active 记录时停止并要求核查，防止未知运行重复执行；人工确认结果后清理 active 或建立新的重试 Run。输出日志保留在 `.xunxu-runs/{job_id}`，回传末尾 10 KB、退出码与 SHA256；失败不覆盖节点研究结论。
