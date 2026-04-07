# 文档入口

这个目录用于放对外公开的项目文档，目标读者是：

- 想快速部署并使用项目的普通用户
- 想基于仓库继续开发的贡献者
- 想把 Web、CLI、Docker、移动端能力串起来的协作者

## 推荐阅读顺序

1. [README.md](../README.md)：项目概览、安装方式、核心命令
2. [docker-deployment.md](docker-deployment.md)：Docker 一键部署的整理方向
3. [input-expansion-roadmap.md](input-expansion-roadmap.md)：分享链接识别、多端入口和 APK 路线

## 文档分层约定

| 路径 | 用途 | 是否计划公开 |
| --- | --- | --- |
| `README.md` | GitHub 首页与快速上手 | 是 |
| `docs/` | 稳定后的公开说明、路线图、部署文档 | 是 |
| `doc/` | 内部草稿、临时方案、开发备忘 | 否 |

这个约定的重点不是“把文档越写越多”，而是让每份文档都有明确角色：

- 首页负责降低第一次使用门槛
- `docs/` 负责承接更完整的说明
- `doc/` 允许继续保留还没定稿的想法，不影响对外观感

## 当前建议的公开文档清单

- `README.md`
- `docs/docker-deployment.md`
- `docs/input-expansion-roadmap.md`

后续功能稳定后，可以再补这些：

- `docs/configuration.md`：环境变量、模型配置、Cookies 配置
- `docs/cli.md`：命令行详解与自动化示例
- `docs/api.md`：Web API 与移动端接入说明
- `docs/contributing.md`：贡献说明与开发流程
