# 幕库文档入口

这个目录用于放幕库对外公开的项目文档，目标读者是：

- 想快速部署并使用项目的普通用户
- 想基于仓库继续开发的贡献者
- 想把 Web、CLI、Docker、Skill 串起来的协作者

## 推荐阅读顺序

1. [README.md](../README.md)：项目概览、安装方式、核心命令
2. [cli.md](cli.md)：CLI、AI 集成、批量与知识库工作流
3. [docker-deployment.md](docker-deployment.md)：Docker 一键部署、容器内 CLI、自检与升级
4. [platform-integration-evaluation.md](platform-integration-evaluation.md)：抖音 / 视频号整合评估
5. [input-expansion-roadmap.md](input-expansion-roadmap.md)：分享链接识别、多端入口和 APK 路线
6. [../skills/README.md](../skills/README.md)：公开 skill 目录与安装方式

## 文档分层约定

| 路径 | 用途 | 是否计划公开 |
| --- | --- | --- |
| `README.md` | GitHub 首页与快速上手 | 是 |
| `docs/` | 稳定后的公开说明、路线图、部署文档 | 是 |
| `doc/` | 内部草稿、临时方案、开发备忘 | 否 |

这个约定的重点不是“把文档越写越多”，而是让每份文档都有明确角色：

- 首页负责降低第一次使用门槛
- `docs/cli.md` 负责承接 AI/脚本/批量工作流
- `docs/docker-deployment.md` 负责承接部署与运维说明
- `docs/platform-integration-evaluation.md` 负责承接多平台接入判断
- `doc/` 允许继续保留还没定稿的想法，不影响对外观感
