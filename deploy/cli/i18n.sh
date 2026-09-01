#!/usr/bin/env bash

movo_detect_locale() {
  local requested="${MOVO_LANG:-en}"
  requested="$(printf '%s' "${requested}" | tr '[:upper:]' '[:lower:]')"
  case "${requested}" in
    zh|zh-*|zh_*|cn|chinese)
      MOVO_LOCALE=zh
      ;;
    *)
      MOVO_LOCALE=en
      ;;
  esac
}

movo_usage() {
  if [[ "${MOVO_LOCALE}" == "zh" ]]; then
    printf '用法：\n'
    printf '  ./movo [--lang zh-CN|en] up [--build]  启动 MOVO 并输出初始化地址\n'
    printf '  ./movo status                         查看服务状态\n'
    printf '  ./movo logs [服务名]                  查看日志\n'
    printf '  ./movo restart                        重启服务\n'
    printf '  ./movo down                           停止服务（保留数据卷）\n'
    printf '  ./movo down -v                        停止服务并删除全部 MOVO 数据\n'
  else
    printf 'Usage:\n'
    printf '  ./movo [--lang zh-CN|en] up [--build]  Start MOVO and print the setup URL\n'
    printf '  ./movo status                          Show service status\n'
    printf '  ./movo logs [service]                  Show logs\n'
    printf '  ./movo restart                         Restart services\n'
    printf '  ./movo down                            Stop services and preserve volumes\n'
    printf '  ./movo down -v                         Stop services and delete all MOVO data\n'
  fi
}

movo_msg() {
  local key="$1"
  shift
  case "${MOVO_LOCALE}:${key}" in
    zh:docker_missing) printf '错误：未找到 Docker，请先安装 Docker Engine 或 Docker Desktop。\n' ;;
    en:docker_missing) printf 'Error: Docker was not found. Install Docker Engine or Docker Desktop first.\n' ;;
    zh:compose_missing) printf '错误：未找到 Docker Compose v2。\n' ;;
    en:compose_missing) printf 'Error: Docker Compose v2 was not found.\n' ;;
    zh:docker_stopped) printf '错误：Docker 尚未运行，请先启动 Docker。\n' ;;
    en:docker_stopped) printf 'Error: Docker is not running. Start Docker first.\n' ;;
    zh:waiting) printf '\n正在等待服务健康检查' ;;
    en:waiting) printf '\nWaiting for deployment health checks' ;;
    zh:done) printf ' 完成\n' ;;
    en:done) printf ' done\n' ;;
    zh:timeout) printf '\n服务未在预期时间内全部就绪。请执行 ./movo status 和 ./movo logs 查看原因。\n' ;;
    en:timeout) printf '\nServices did not become ready in time. Run ./movo status and ./movo logs for details.\n' ;;
    zh:ready_title) printf '\nMOVO 已启动。请在浏览器中完成首次初始化：\n\n' ;;
    en:ready_title) printf '\nMOVO is running. Complete the initial setup in your browser:\n\n' ;;
    zh:starting) printf '正在启动 MOVO 服务...\n' ;;
    en:starting) printf 'Starting MOVO services...\n' ;;
    zh:dsh_build_target) printf 'DSH Runtime 目标构建版本：%s\n' "$1" ;;
    en:dsh_build_target) printf 'DSH Runtime build target: %s\n' "$1" ;;
    zh:dsh_running_version) printf 'DSH Runtime 运行版本：%s\n' "$1" ;;
    en:dsh_running_version) printf 'DSH Runtime running version: %s\n' "$1" ;;
    zh:migrating_project) printf '正在迁移旧版 Compose 服务名（数据卷会保留）...\n' ;;
    en:migrating_project) printf 'Migrating the legacy Compose project name (data volumes are preserved)...\n' ;;
    zh:start_failed) printf '\nMOVO 启动失败，当前服务状态如下：\n' ;;
    en:start_failed) printf '\nMOVO failed to start. Current service status:\n' ;;
    zh:logs_hint) printf '请执行 ./movo logs 查看详细日志。\n' ;;
    en:logs_hint) printf 'Run ./movo logs for detailed logs.\n' ;;
    zh:stopped) printf 'MOVO 已停止，数据卷仍然保留。\n' ;;
    en:stopped) printf 'MOVO has stopped. Data volumes are preserved.\n' ;;
    zh:stopped_removed) printf 'MOVO 已停止，数据卷和初始化数据已删除。\n' ;;
    en:stopped_removed) printf 'MOVO has stopped. Data volumes and setup state were deleted.\n' ;;
    zh:unknown) printf '未知命令：%s\n\n' "$1" ;;
    en:unknown) printf 'Unknown command: %s\n\n' "$1" ;;
    *) printf '%s' "${key}" ;;
  esac
}
