# QuickStart

```bash
PROMPT=$(cat <<'EOF'
现在我们要从头开始创建一个叫 closeclaw 的项目，这个项目是一个把 AI Agent 绑定到 Telegram 上的作用，有如下功能：

1. 有一个 Telegram Bot，用户可以通过 Telegram 与它交互，包括发送消息、命令等。
2. 有一个 AI Agent loop，能够接收用户消息，有一个工具集 (最简单版本可以是一个 Bash)，这个 loop 用 kosong 实现，可以看 kosong 源码，里面有丰富的示例。
3. 有一个 debug 用的 cli，给开发者（以及你自己）用来调试 telegram 或 agent loop

请设计合理的架构，我个人建议把 agent-loop 部分叫做 agent_core 模块，telegram 部分放到 channels 模块

技术选型：
- 请使用 pydantic-settings 管理配置，配置内容通过 dotenv 或 yaml 文件获取，并且支持环境变量覆盖。
- 用 loguru 和 rich 来处理命令行交互，cli 用 click 来实现。
- agent model 使用 moonshot/kimi-k2.5
- 网络部分，一律使用 asyncio

先制订一个计划，然后写一个最小实现，然后要自己测试一下，然后和模型交互需要 model provider 和 api_key 等配置，telegram bot 也需要 bot token, allowed_users 等配置，
api_key 和 token 要从环境变量获取，你写一个 .env 文件，结构留好，在必要的时候停下来问我 KEY 和 token 的具体值。
EOF)

kimi --yolo -c $PROMPT
```
