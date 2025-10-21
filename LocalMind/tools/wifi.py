import subprocess, json, re

def wifi_info(timeout_seconds: int = 6):
    try:
        # netsh is present on Windows; no admin needed to scan
        cmd = ["netsh", "wlan", "show", "networks", "mode=bssid"]
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds, check=False)
        if cp.returncode != 0:
            return {"ok": False, "error": cp.stderr.strip() or "netsh returned non-zero"}

        txt = cp.stdout
        networks = []
        current = None
        for line in txt.splitlines():
            line = line.strip()
            m_ssid = re.match(r"SSID \d+\s*:\s*(.*)", line, re.IGNORECASE)
            if m_ssid:
                if current:
                    networks.append(current)
                current = {"ssid": m_ssid.group(1).strip(), "bssids": []}
                continue
            if current is None:
                continue

            m_auth = re.match(r"Authentication\s*:\s*(.*)", line, re.IGNORECASE)
            if m_auth:
                current["authentication"] = m_auth.group(1).strip(); continue

            m_cipher = re.match(r"Encryption\s*:\s*(.*)", line, re.IGNORECASE)
            if m_cipher:
                current["encryption"] = m_cipher.group(1).strip(); continue

            m_bssid = re.match(r"BSSID \d+\s*:\s*(.*)", line, re.IGNORECASE)
            if m_bssid:
                current["bssids"].append({"bssid": m_bssid.group(1).strip()}); continue

            m_signal = re.match(r"Signal\s*:\s*(\d+)%", line, re.IGNORECASE)
            if m_signal and current.get("bssids"):
                current["bssids"][-1]["signal_percent"] = int(m_signal.group(1)); continue

            m_channel = re.match(r"Channel\s*:\s*(\d+)", line, re.IGNORECASE)
            if m_channel and current.get("bssids"):
                current["bssids"][-1]["channel"] = int(m_channel.group(1)); continue

        if current:
            networks.append(current)

        return {"ok": True, "results_count": len(networks), "networks": networks}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    
