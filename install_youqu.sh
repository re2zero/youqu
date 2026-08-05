#!/bin/bash
# SPDX-FileCopyrightText: 2023 - 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
#
# youqu-ai 一键安装脚本
#
# 从 GitLab 内网仓库 https://gitlabcd.uniontech.com/ut003403/youqu-ai 的 dist 目录
# 下载最新 wheel 包, 并使用 pipx 安装 (支持 --system-site-packages 以复用
# apt 安装的系统 Python 包, 如 gi / pyatspi 等)。
#
# 用法:
#   bash install_youqu.sh                     # 交互式确认后安装
#   bash install_youqu.sh -y                  # 跳过所有确认
#   bash install_youqu.sh -p PASSWORD         # 指定 sudo 密码(用于安装系统依赖)
#   bash install_youqu.sh -v 2.18.6           # 指定版本(默认最新)
#   bash install_youqu.sh -U user:password    # GitLab 需要认证时指定
#   bash install_youqu.sh -t PRIVATE_TOKEN    # 或指定 GitLab 私有令牌
#   bash install_youqu.sh -i INDEX_URL        # 指定 pip 镜像(默认清华)
#   bash install_youqu.sh -n                  # 跳过系统依赖安装
#   bash install_youqu.sh -h                  # 帮助
#
# 环境变量:
#   GITLAB_BASE_URL / GITLAB_PROJECT / GITLAB_BRANCH / GITLAB_USER / GITLAB_TOKEN / PIP_INDEX_URL 可替代对应参数

set -u

GITLAB_BASE_URL="${GITLAB_BASE_URL:-https://gitlabcd.uniontech.com}"
GITLAB_PROJECT="${GITLAB_PROJECT:-ut003403%2Fyouqu-ai}"
GITLAB_BRANCH="${GITLAB_BRANCH:-main}"
GITLAB_DIST="dist"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
WORKDIR="${TMPDIR:-/tmp}/youqu-install"

ASSUME_YES=false
INSTALL_SYSTEM_DEPS=true
FORCE_VERSION=""
GITLAB_USER="${GITLAB_USER:-}"
GITLAB_TOKEN="${GITLAB_TOKEN:-}"
SUDO_PASSWORD=""

# 远程管道执行 (bash -c "$(curl ...)") 或 stdin 模式时, 无法交互确认, 默认自动确认
if [ ! -t 0 ] && [ "${ASSUME_YES}" = "false" ]; then
    ASSUME_YES=true
fi

WHEEL_PATH=""

usage() {
    cat <<'EOF'
youqu-ai 一键安装脚本 — 从 GitLab 内网仓库下载最新 wheel 并使用 pipx 安装。

用法:
  bash -c "$(curl -fsSL <raw-url>/install_youqu.sh)"    # 远程一键安装(默认自动确认)
  bash install_youqu.sh                                # 本地安装(交互式确认)
  bash install_youqu.sh -y                             # 跳过所有确认
  bash install_youqu.sh -p PASSWORD                    # 指定 sudo 密码(安装系统依赖)
  bash install_youqu.sh -v 2.18.6                      # 指定版本(默认最新)
  bash install_youqu.sh -U user:password               # GitLab 需要认证时指定
  bash install_youqu.sh -t PRIVATE_TOKEN               # 或指定 GitLab 私有令牌
  bash install_youqu.sh -i INDEX_URL                   # 指定 pip 镜像(默认清华)
  bash install_youqu.sh -n                             # 跳过系统依赖安装
  bash install_youqu.sh -h                             # 帮助

环境变量:
  GITLAB_BASE_URL / GITLAB_PROJECT / GITLAB_BRANCH / GITLAB_USER / GITLAB_TOKEN / PIP_INDEX_URL 可替代对应参数
EOF
}

while getopts ":yp:v:U:t:i:nh" opt; do
    case ${opt} in
        y) ASSUME_YES=true ;;
        p) SUDO_PASSWORD="${OPTARG}" ;;
        v) FORCE_VERSION="${OPTARG}" ;;
        U) GITLAB_USER="${OPTARG}" ;;
        t) GITLAB_TOKEN="${OPTARG}" ;;
        i) PIP_INDEX_URL="${OPTARG}" ;;
        n) INSTALL_SYSTEM_DEPS=false ;;
        h) usage; exit 0 ;;
        \?) echo "未知参数: -${OPTARG}"; usage; exit 1 ;;
        :) echo "参数 -${OPTARG} 缺少值"; usage; exit 1 ;;
    esac
done
shift $((OPTIND - 1))

log()  { echo -e "\033[32m[youqu-install]\033[0m $*"; }
warn() { echo -e "\033[33m[youqu-install]\033[0m $*"; }
die()  { echo -e "\033[31m[youqu-install]\033[0m 错误: $*" >&2; exit 1; }

confirm() {
    if [ "${ASSUME_YES}" = "true" ]; then
        return 0
    fi
    local prompt="$1"
    read -r -p "${prompt} [y/N] " answer
    case "${answer}" in
        y|Y|yes|YES) return 0 ;;
        *) return 1 ;;
    esac
}

sudo_exec() {
    # 优先用 -p 密码, 否则退化为普通 sudo(交互式输入)
    if [ -n "${SUDO_PASSWORD}" ]; then
        echo "${SUDO_PASSWORD}" | sudo -S "$@" > /dev/null 2>&1
    else
        sudo "$@" > /dev/null 2>&1
    fi
}

need_sudo() {
    if [ "$(id -u)" = "0" ]; then
        return 0
    fi
    if [ -n "${SUDO_PASSWORD}" ]; then
        echo "${SUDO_PASSWORD}" | sudo -S true > /dev/null 2>&1
    else
        sudo -n true > /dev/null 2>&1
    fi
}

# ---------------------------------------------------------------- 系统依赖
install_system_deps() {
    local pm=""
    if command -v apt > /dev/null 2>&1; then
        pm=apt
    elif command -v yum > /dev/null 2>&1; then
        pm=yum
    else
        warn "未识别的包管理器(仅支持 apt/yum), 跳过系统依赖安装"
        return 0
    fi

    if ! need_sudo; then
        warn "无法获取 sudo 权限, 跳过系统依赖安装 (可用 -p 指定密码)"
        return 0
    fi

    log "安装系统依赖 (${pm}) ..."
    local deb_array=(
        python3-pip
        python3-tk
        scrot
        openjdk-11-jdk-headless
        gir1.2-atspi-2.0
        libatk-adaptor
        at-spi2-core
        python3-opencv
    )
    local rpms=(
        java-11-openjdk-headless
        python3-tkinter
        xdotool
        opencv
    )

    if [ "${pm}" = "apt" ]; then
        sudo_exec apt update || true
        for deb in "${deb_array[@]}"; do
            log "  apt install -y ${deb}"
            sudo_exec apt install -y "${deb}" || warn "  安装 ${deb} 失败(可忽略, 部分缺失仅影响对应能力)"
        done
    else
        for rpm in "${rpms[@]}"; do
            log "  yum install -y ${rpm}"
            sudo_exec yum install -y "${rpm}" || warn "  安装 ${rpm} 失败(可忽略)"
        done
    fi

    # Wayland 附加依赖
    local session_type="${XDG_SESSION_TYPE:-}"
    if [ -z "${session_type}" ] && [ -n "${DISPLAY:-}" ]; then
        session_type="x11"
    fi
    if [ "${session_type}" = "wayland" ]; then
        log "检测到 Wayland 会话, 安装附加依赖 ..."
        if [ "${pm}" = "apt" ]; then
            for deb in g++ build-essential cmake qt5-default qt5-qmake libqt5gui5 libqt5core5a wl-clipboard; do
                sudo_exec apt install -y "${deb}" || warn "  安装 ${deb} 失败(可忽略)"
            done
        fi
        warn "Wayland 下 wayland_autotool 为编译安装, 请参考仓库 docs 或 env.sh 手动编译; 未编译时框架自动降级"
    fi
}

# ---------------------------------------------------------------- 下载 wheel
download_wheel() {
    mkdir -p "${WORKDIR}" || die "无法创建临时目录 ${WORKDIR}"

    local curl_args=(-fsSL -m 300)
    if [ -n "${GITLAB_USER}" ]; then
        curl_args+=(--user "${GITLAB_USER}")
    elif [ -n "${GITLAB_TOKEN}" ]; then
        curl_args+=(-H "PRIVATE-TOKEN: ${GITLAB_TOKEN}")
    fi

    local api_base="${GITLAB_BASE_URL}/api/v4/projects/${GITLAB_PROJECT}/repository"

    # 1) 取 dist 目录文件列表, 解析出最新版本
    log "查询 ${GITLAB_BASE_URL}/${GITLAB_PROJECT%%%2F*}/${GITLAB_PROJECT##*%2F}/-/tree/${GITLAB_BRANCH}/${GITLAB_DIST} 下的 wheel 包 ..."
    local listing
    listing=$(curl "${curl_args[@]}" "${api_base}/tree?path=${GITLAB_DIST}&ref=${GITLAB_BRANCH}&per_page=100" 2>/dev/null) \
        || die "无法获取 dist 目录列表, 请检查网络或认证 (-U/-t)"

    local versions
    versions=$(printf '%s' "${listing}" \
        | python3 -c '
import json, sys, re
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
names = [d.get("name", "") for d in data if d.get("type") == "blob" and d.get("name", "").endswith(".whl")]
if not names:
    sys.exit(1)
vers = []
for n in names:
    m = re.match(r"youqu_ai-(\d+\.\d+\.\d+)-py3-none-any\.whl", n)
    if m:
        vers.append(tuple(int(x) for x in m.group(1).split(".")))
vers.sort()
print(".".join(str(x) for x in vers[-1]) if vers else "")
') || die "解析 dist 目录列表失败"

    if [ -z "${versions}" ]; then
        die "dist 目录下未找到 youqu_ai-*.whl 包"
    fi

    local version="${FORCE_VERSION:-${versions}}"
    local wheel_name="youqu_ai-${version}-py3-none-any.whl"
    local download_url="${api_base}/files/${GITLAB_DIST}%2F${wheel_name}/raw?ref=${GITLAB_BRANCH}"
    local wheel_path="${WORKDIR}/${wheel_name}"

    log "下载 ${wheel_name} ..."
    curl "${curl_args[@]}" -o "${wheel_path}" "${download_url}" || die "下载 ${download_url} 失败"

    # 校验是合法的 zip (wheel)
    python3 -c "import zipfile; zipfile.ZipFile('${wheel_path}')" 2>/dev/null \
        || die "下载的文件不是合法的 wheel 包, 请检查版本/认证"

    log "下载完成: ${wheel_path} ($(du -h "${wheel_path}" | cut -f1))"
    WHEEL_PATH="${wheel_path}"
}

# ---------------------------------------------------------------- pipx 安装
install_with_pipx() {
    local wheel_path="$1"

    if ! command -v pipx > /dev/null 2>&1; then
        log "未检测到 pipx, 正在安装 ..."
        if ! need_sudo; then
            die "安装 pipx 需要 sudo 权限 (可用 -p 指定密码)"
        fi
        if command -v apt > /dev/null 2>&1; then
            sudo_exec apt install -y pipx || die "apt 安装 pipx 失败"
        elif command -v yum > /dev/null 2>&1; then
            sudo_exec yum install -y pipx || die "yum 安装 pipx 失败"
        else
            python3 -m pip install --user --break-system-packages pipx || die "pip 安装 pipx 失败"
        fi
        # pipx 自带的 shell 补全/路径, 重新查找
        export PATH="${PATH}:${HOME}/.local/bin"
        command -v pipx > /dev/null 2>&1 || die "pipx 安装后仍不可用, 请检查 PATH"
    fi

    log "使用 pipx 安装 ${wheel_path##*/} ..."
    # --system-site-packages: 复用 apt 安装的系统 Python 包 (gi, pyatspi, dbus 等)
    # --force: 同版本已安装时强制覆盖, 保证重装/升级生效
    # --pip-args: 指定 pip 镜像与不校验依赖版本冲突
    pipx install \
        --system-site-packages \
        --force \
        --pip-args "--index-url ${PIP_INDEX_URL} --no-input" \
        "${wheel_path}" || die "pipx 安装失败, 可尝试手动执行: pipx install --system-site-packages --force ${wheel_path}"

    log "验证安装 ..."
    command -v youqu > /dev/null 2>&1 || export PATH="${PATH}:${HOME}/.local/bin"
    if ! command -v youqu > /dev/null 2>&1; then
        warn "youqu 命令不在 PATH 中, 请执行: export PATH=\"\${PATH}:${HOME}/.local/bin\" 或重新登录"
    else
        log "youqu 命令可用: $(command -v youqu)"
        youqu --help > /dev/null 2>&1 && log "youqu 运行正常" || warn "youqu 已安装但运行报错, 请查看上方输出"
    fi
}

# ---------------------------------------------------------------- 环境变量
setup_env() {
    log "配置环境变量 (DISPLAY / 无障碍) ..."
    local rc="${HOME}/.bashrc"
    local lines=(
        'export DISPLAY=":0"'
        'export QT_QPA_PLATFORM='
        'export QT_ACCESSIBILITY=1'
        'export QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1'
    )
    for line in "${lines[@]}"; do
        if ! grep -qF "${line}" "${rc}" 2>/dev/null; then
            echo "${line}" >> "${rc}"
        fi
    done
    export DISPLAY="${DISPLAY:-:0}"
    export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-}"
    export QT_ACCESSIBILITY=1
    export QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1
    gsettings set org.gnome.desktop.interface toolkit-accessibility true > /dev/null 2>&1 \
        && log "已开启 GNOME 无障碍" || true
}

# ================================================================ 主流程
main() {
    log "youqu-ai 一键安装脚本"
    log "GitLab: ${GITLAB_BASE_URL}/${GITLAB_PROJECT%%%2F*}/${GITLAB_PROJECT##*%2F} 分支: ${GITLAB_BRANCH}"

    if [ "${INSTALL_SYSTEM_DEPS}" = "true" ]; then
        install_system_deps
    fi

    download_wheel
    local wheel_path="${WHEEL_PATH}"
    [ -n "${wheel_path}" ] && [ -f "${wheel_path}" ] || die "未获取到 wheel 包路径"

    confirm "即将使用 pipx 安装 ${wheel_path##*/}, 继续?" || { warn "已取消"; exit 0; }
    install_with_pipx "${wheel_path}"
    setup_env

    log "安装完成! 运行 youqu manage.py -h 或 youqu doctor 验证环境。"
}

main "$@"
