# Proton-CachyOS-TUN：五补丁实验分支

## 定位和当前状态

这是个人自用实验 fork，不是 CachyOS 或 WE-Proton 官方发行。保留 CachyOS 原有 Wine、DXVK、VKD3D、protonfixes 等组件的 gitlink，仅引入网络相关的五个 WE 补丁。

**当前完成的是源码集成和静态应用验证，不是可用 runner 发布。尚未完整编译、打包或启动 Windows 加速器，也没有目标游戏流量、性能或反作弊验证。** 不应把本仓库的源码检查 CI 绿色当作加速成功。

## 固定来源

| 内容 | 固定提交 |
| --- | --- |
| [Proton-CachyOS 基线](https://github.com/CachyOS/proton-cachyos/tree/4b3d2918bd8d6880451f012bf2ced4e337447083) | `4b3d2918bd8d6880451f012bf2ced4e337447083` |
| [CachyOS Wine gitlink](https://github.com/CachyOS/wine-cachyos/tree/6a7adb2adf750046ad01091b369ea95c8b551a30) | `6a7adb2adf750046ad01091b369ea95c8b551a30` |
| [WE-Proton 补丁来源](https://github.com/SHORiN-KiWATA/we-proton/tree/8cfdd8c45c6d6c2d92ecd8f118fb03e0a28b08a7/patches/wine) | `8cfdd8c45c6d6c2d92ecd8f118fb03e0a28b08a7` |

补丁保持来源字节、提交头、作者信息和文件内许可声明；不删除或重新授权上游内容。Wine 源码遵循各文件的原始许可证。维护时需继续遵守相应许可证和源码提供义务。

严格按以下顺序应用，不引入 WeGame UI、IME、窗口管理或图形补丁：

1. **0015**：IP Helper / NSI / netlink 的地址和路由配置路径。
2. **0016**：内置 Wintun PE DLL + Unix 库，把 Wintun 用户态 API 映射到 Linux `/dev/net/tun`；不是加载 Windows 内核驱动。
3. **0017**：TCP `IP_UNICAST_IF` 与 `SO_BINDTODEVICE`，处理直接出站连接回流 TUN 的问题；权限失败和 IPv6 行为仍需实测。
4. **0048**：Wintun 适配器描述，满足部分加速器识别需求。
5. **0053**：实现旧版 `CreateIpForwardEntry` / `SetIpForwardEntry` / `DeleteIpForwardEntry`，而不是仅返回成功。

完整文件名、来源 URL、SHA-256、19 个涉及文件的原始/补丁后 SHA-256 均记录在 [manifest](../patches/wine-tun/manifest.json)。六个新 Wintun 文件的原始 SHA 为 `null`，表示该固定基线中不存在。

## 构建接入方式

[Makefile.in](../Makefile.in) 的 `.wine-post-source` 步骤调用 [apply.py](../tools/tun/apply.py)：

```text
原始 Wine submodule → rsync 到 OBJ/src-wine
    → 验证 Wine HEAD / Proton gitlink / 补丁顺序、数量、哈希 / 涉及文件内容
    → 私有临时目录内顺序 git apply --check，再 apply
    → 核对最终文件哈希后写入构建副本
    → 原有 Wine post-source 生成步骤 → 成功后 stamp
    → autoreconf → configure → 原有编译/打包步骤
```

- 不修改原始 Wine submodule，不创建第二个 Wine fork，也没有引用未推送的 Wine 对象。
- 仅涉及文件匹配固定基线才应用；全部匹配预期补丁后内容时幂等返回；混合、部分应用、未知修改、缺失或多余补丁均拒绝继续。
- 全系列预检失败不会向目标源码写入前几个补丁。最终复制阶段不是跨文件原子事务；若磁盘/进程错误导致写入中断，下次检查会拒绝混合状态，需重新同步干净的构建副本。
- `configure` 对 post-source stamp 使用普通依赖，保证修改 `configure.ac` 后先重新生成配置，再配置/编译。
- 未来更新基线必须重新验证并更新 manifest 和固定常量；不能为“通过构建”忽略检查、自动拉取其他 Wine 提交或模糊应用补丁。

## 检查与证据边界

在本次集成工作目录实际执行并通过：

```bash
python3 -m unittest discover -s tools/tun -p 'test_*.py' -v
python3 tools/tun/verify.py
git diff --check
```

- 单元测试验证预检无修改、应用、重复应用、错误来源、补丁哈希/顺序/数量、部分状态、迟发 hunk 失败和符号链接拒绝等失败路径。
- `verify.py` 从上述固定 Wine 提交重新获取涉及的已有文件，并与 manifest 比对；验证五补丁顺序应用及幂等。它只获取涉及文件，不是完整 Wine checkout 或编译。
- [TUN source checks CI](../.github/workflows/tun-patches.yml) 自动执行同类检查，不启动加速器、不创建 TUN、不改网络、不生成 runner 二进制。
- 尚未验证：完整 submodule 检出、所有架构/工具链编译、PE/Unix 库安装产物、运行时 DLL 选择、netlink 权限、真实 UDP/TCP 数据转发、DNS 和清理恢复。

## 后续完整构建

需要可用 Docker/Podman、Steam Runtime 构建镜像、全部 submodule 和足够资源；依赖、容器和主机构建要求以保留的上游说明为准。下面是待运行的构建步骤，本次未执行：

```bash
git clone --branch tun/cachyos-11.0-20261014 https://github.com/AL-A-V-Parseval/Proton-CachyOS-TUN.git
cd Proton-CachyOS-TUN
git submodule update --init --filter=tree:0 --recursive
mkdir build
cd build
../configure.sh --build-name=Proton-CachyOS-TUN-11.0-20261014 --container-engine=docker
make redist
```

若固定 gitlink 在远端无法获取，构建应停止并调查，不替换成另一提交。上游 Snapshot 手动工作流仍保留，但涉及多架构构建，不会因本实验分支 push 自动启动；本次未启动它。

## 运行安全边界（待编译后验证）

- 配合 [proton-wrapper](https://github.com/SHORiN-KiWATA/proton-wrapper) 的 `--netns on` / pasta 会话，在专用 prefix 内先启动加速器，再启动目标程序。不要以宿主 root 运行；本 fork 不会自动创建隔离环境。
- 需要内核 TUN、用户/网络命名空间和对应命名空间内网络管理权限；容器/发行版安全策略可能限制。不能因此认为所有 Windows 驱动、WFP/NDIS 加速器都受支持。
- wrapper 通常指定 `WINEDLLOVERRIDES=...;wintun=b`；其他启动方式不能假设会选择内置实现。不要盲目覆盖现有 DLL 配置。
- 测试用独立 prefix，先检查 `/dev/net/tun`、接口、路由、DNS，再确认实际游戏流量进入隧道及远端响应。GUI“加速中”、TUN 存在或 API 返回成功均不是充分证据。
- 当前 Clash 仅代理端口、不启用 TUN 时，不会自动代理所有网络连接；命名空间内 `127.0.0.1` 不等于宿主 loopback，继承代理和 DNS 配置需另行核对。
- 不支持或承诺反作弊兼容/绕过，尤其不能把 TUN 补丁视为 ACE 等内核反作弊解决方案。联网游戏仍有账号和封禁风险。
- 测试退出后确认会话、TUN、路由和 DNS 清理；没有额外授权时不要在宿主网络里测试加速器。
