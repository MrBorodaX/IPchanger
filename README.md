# 🌐 IPChanger

**IPChanger** is a convenient desktop application for quickly managing network configurations on Windows. It allows you to save, apply, and switch between different IP address, subnet mask, and gateway settings for network interfaces with a single click.

## ✨ Features

###  Core
- 🔄 **Quick switching** between network profiles via double-click
- 💾 **Auto-saving** configurations to a JSON file
- 📋 **Cloning** existing configurations
- 🎨 **Color-coded status indicators**:
  - 🟢 Green — configuration applied and active
  - ⚪ Gray — inactive configuration
  - 🔴 Red — interface disabled or no connection
- 📐 **Adaptive grid** — number of columns adjusts to window size

###  Network Functions
- 📡 **Active adapter monitoring** in real-time, displaying IP/CIDR and gateway
- 🔁 **Manual interface list refresh** (F5) — useful when connecting new adapters
-  **Ping gateway** in a separate console window
- 🖥️ **Run `ipconfig /all`** to view all network settings
- 🛡️ **Subnet overlap check** before applying
-  **DHCP and static IP support**
- 🧮 **Automatic calculation** of subnet mask and gateway when entering CIDR (e.g., `192.168.1.100/24`)

### 🖼️ Interface
-  **Windows Dark Theme support** — the app adapts to system settings
- 🎨 **Pastel colors** — easy on the eyes design
- ️ **Context menu** for quick access to all functions
- ⌨️ **Hotkeys** for all major actions

### 🔐 Security
- 🛡️ **Administrator privilege check** on startup with a warning
- ⚠️ **Input validation** for IP addresses and masks

---

## 📋 Requirements

| Component | Version |
|---|---|
| **OS** | Windows 10 / 11 |
| **Python** | 3.8+ |
| **PySide6** | 6.x |
| **Privileges** | Administrator (to apply settings) |
| **Language** | Ru |
---

## ⚙️ Installation

### 1. Clone the repository

```bash
git clone https://github.com/MrBorodaX/IPChanger.git
cd IPChanger
```

### 2. Create a virtual environment (recommended)

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Or manually:

```bash
pip install PySide6
```

### 4. Run the application

```bash
python main.py
```

### 🚀 Run as Administrator (recommended)

```powershell
# PowerShell
Start-Process python -ArgumentList "main.py" -Verb RunAs

# CMD
runas /user:Administrator python main.py
```

---

## 📖 Usage

### 🎮 Basic Actions

| Action | Method |
|---|---|
| Apply configuration | **Double-click** on the header |
| Context menu | **Right-click** on the header |
| Add configuration | `+ Add configuration` button |
| Refresh interfaces | Menu **Network → ⟳ Refresh** or `F5` |
| Ping gateway | Menu **Network → Ping Gateway** or `Ctrl+P` |
| IPConfig | Menu **Network → IPConfig** or `Ctrl+I` |
| Save | `Ctrl+S` |
| New configuration | `Ctrl+N` |
| Open file | `Ctrl+O` |
| Help | `F1` |


###  Configuration Context Menu

- **Edit** — rename the configuration
- **Apply** — apply settings to the selected interface
- **Delete** — delete the configuration
- **Clone** — create a copy of the configuration
- **DHCP** — set to obtain IP automatically
- **Ping** — run ping to the gateway or IP
- **Enable / Disable** — manage interface state

---

## 🏗️ Project Structure

```
IPChanger/
├── main.py                  # Main application file
├── configurations.json      # Saved configurations file (created automatically)
├── icon.ico                 # Application icon
├── README.md                # Documentation
└── LICENSE                  # License
```

### ️ Code Architecture

| Class | Purpose |
|---|---|
| `NetworkManager` | Network interface management via `netsh` |
| `ConfigManager` | Saving and loading configurations from JSON |
| `ConfigWidget` | Widget for a single network configuration |
| `ActiveConfigWidget` | Widget displaying an active configuration |
| `MainWindow` | Main application window with menu |

---

## 🛠️ Technologies

- **[Python 3.8+](https://www.python.org/)** — Programming language
- **[PySide6](https://doc.qt.io/qtforpython-6/)** — GUI framework (Qt 6)
- **netsh** — Windows network interface management
- **ipaddress** — Standard library for working with IP addresses and subnets
- **subprocess** — Interaction with system commands

---

## 📦 Building to .exe

To create a standalone executable file:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icon.ico --name=IPChanger main.py
```

The final file will appear in the `dist/` folder.

---

##  Administrator Privileges

Administrator privileges are **required** to apply network settings and enable/disable interfaces. If run without admin rights, the application will show a warning but will still allow you to work in view-only mode.

---

## ⚠️ Known Limitations

- ⚠️ Works only on **Windows** (uses `netsh`)
- ⚠️ Requires **Windows 10/11** for correct handling of Russian interface names
- ⚠️ Changing settings requires **Administrator privileges**
- ⚠️ Firewall permission may be required on the first run

---

##  Contributing

**Pull requests** and **issues** are welcome! 

### How to help the project:

1. **Found a bug?** — create an [Issue](https://github.com/MrBorodaX/IPChanger/issues) with a detailed description
2. **Have an idea?** — open a [Discussion](https://github.com/MrBorodaX/IPChanger/discussions)
3. **Want to improve the code?** — make a Fork and submit a Pull Request

### Contributing Process:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

##  License

This project is licensed under the GNU General Public License v3.0.
See the [LICENSE](LICENSE) file for details.

© 2026 MrBorodaX

---

## 👤 Author

**MrBorodaX**

- GitHub: [@MrBorodaX](https://github.com/MrBorodaX)

---

## 📬 Contact

If you have any questions or suggestions, please create an Issue in the repository.

---

## ⭐ Support the Project

If this project helped you, please **star** ⭐ the repository! It's the best support for the developer.

<p align="center">
  <b>Made with ❤️ for Windows users</b>
</p>

---

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-blue" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/PySide6-6.x-green" alt="PySide6">
  <img src="https://img.shields.io/badge/Platform-Windows-lightgrey" alt="Windows">
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="License MIT">
</p>
