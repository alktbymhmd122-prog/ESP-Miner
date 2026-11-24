import os
import re

# 1. Safe, idempotent hardware-safe network & stability config
SDK_MARKER = "# === BITAXE_601_SAFE_OPTIMIZATIONS ==="
sdk_additions = f"""
{SDK_MARKER}
CONFIG_FREERTOS_HZ=1000
CONFIG_ESP_WIFI_STATIC_RX_BUFFER_NUM=16
CONFIG_ESP_WIFI_DYNAMIC_RX_BUFFER_NUM=32
CONFIG_ESP_WIFI_DYNAMIC_TX_BUFFER_NUM=32
CONFIG_ESP_WIFI_AMPDU_TX_ENABLED=y
CONFIG_ESP_WIFI_AMPDU_RX_ENABLED=y
CONFIG_LWIP_TCP_NODELAY=y
CONFIG_LWIP_TCPIP_RECVMBOX_SIZE=32
CONFIG_LWIP_TCP_SND_BUF_DEFAULT=16384
CONFIG_LWIP_TCP_WND_DEFAULT=16384
CONFIG_ESP_TASK_WDT_TIMEOUT_S=10
CONFIG_ESP_BROWNOUT_DET=y
CONFIG_COMPILER_OPTIMIZATION_PERF=y
"""

if os.path.exists("sdkconfig.defaults"):
    with open("sdkconfig.defaults", "r") as f:
        sdk_content = f.read()
    if SDK_MARKER not in sdk_content:
        with open("sdkconfig.defaults", "a") as f:
            f.write(sdk_additions)
        print("[OK] sdkconfig.defaults updated.")
    else:
        print("[SKIP] sdkconfig.defaults already patched.")

# 2. Safe Core Pinning (Core 1 = Mining, Core 0 = Network/UI) & Low-Latency Wi-Fi
def patch_c_file(filepath):
    if not os.path.exists(filepath):
        return False
    with open(filepath, "r") as f:
        code = f.read()
    orig_code = code

    # Disable Wi-Fi power-save sleep if esp_wifi_start exists here
    if "esp_wifi_start();" in code and "esp_wifi_set_ps(WIFI_PS_NONE);" not in code:
        code = code.replace(
            "esp_wifi_start();",
            "esp_wifi_start();\n    esp_wifi_set_ps(WIFI_PS_NONE);"
        )

    # Pin tasks safely using balanced-parentheses matching
    task_cores = {
        "asic_result_task": "1",
        "create_jobs_task": "1",
        "miner_job_task": "1",
        "stratum_task": "0",
    }

    for task_name, core_id in task_cores.items():
        pattern = re.compile(rf"\bxTaskCreate\s*\(\s*{task_name}\b")
        match = pattern.search(code)
        if match:
            start = match.start()
            open_paren = code.find("(", start)
            depth = 0
            end_paren = -1
            for i in range(open_paren, len(code)):
                if code[i] == "(":
                    depth += 1
                elif code[i] == ")":
                    depth -= 1
                    if depth == 0:
                        end_paren = i
                        break
            if end_paren != -1:
                call_str = code[start:end_paren + 1]
                new_call = call_str.replace("xTaskCreate", "xTaskCreatePinnedToCore", 1)
                new_call = new_call[:-1] + f", {core_id})"
                code = code[:start] + new_call + code[end_paren + 1:]
                print(f"[OK] Pinned {task_name} -> Core {core_id} in {filepath}")

    if code != orig_code:
        with open(filepath, "w") as f:
            f.write(code)
        return True
    return False

patched_any = False
for root, _, files in os.walk("main"):
    for fn in files:
        if fn.endswith(".c"):
            if patch_c_file(os.path.join(root, fn)):
                patched_any = True

if not patched_any:
    print("[WARN] No target C task calls matched automatically; verify task names in main/.")
else:
    print("[DONE] Pure-software safe optimizations applied.")
