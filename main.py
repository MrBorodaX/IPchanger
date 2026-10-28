import sys
import json
import os
import time
import ipaddress
import subprocess
from dataclasses import dataclass, field
import re
import ctypes
from PySide6 import QtWidgets, QtCore, QtGui

CONFIG_FILE = 'configurations.json'
APP_NAME = "IPChanger"
APP_VERSION = "3.0.1"
DATE = "28.10.2026"

# Пастельные цвета
COLOR_ACTIVE = "#B8E6B8"
COLOR_INACTIVE = "#E8E8E8"
COLOR_ERROR = "#FFB3B3"
COLOR_HEADER_BORDER = "#C0C0C0"
COLOR_ACTIVE_BORDER = "#6BBF6B"
COLOR_ERROR_BORDER = "#D96B6B"


def run_command(command):
    """Выполнить команду через chcp 65001 (UTF-8) для корректной кодировки"""
    try:
        # Принудительно устанавливаем UTF-8 кодировку для команды
        full_command = f'cmd /c chcp 65001 >nul 2>&1 && {command}'
        result = subprocess.run(
            full_command,
            shell=True,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        output = result.stdout.decode('utf-8', errors='replace')
        return output
    except Exception as e:
        print(f"Ошибка выполнения команды: {e}")
        return ""


def is_admin():
    """Проверить, запущено ли приложение от имени администратора"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


@dataclass
class NetworkSnapshot:
    adapters: list = field(default_factory=list)
    active: dict = field(default_factory=dict)
    timestamp: float = 0.0


class NetworkManager:
    """Быстрый доступ к сетевым адаптерам Windows."""

    @staticmethod
    def _powershell_json(script):
        try:
            prefix = (
                "$OutputEncoding = [Console]::OutputEncoding = "
                "New-Object System.Text.UTF8Encoding($false); "
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", prefix + script],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW, check=False,
            )
            raw = result.stdout.decode("utf-8", errors="replace").strip()
            if result.returncode != 0:
                error = result.stderr.decode("utf-8", errors="replace").strip()
                print(f"PowerShell error: {error}")
                return None
            if not raw:
                return []
            return json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Ошибка PowerShell: {exc}")
            return None

    @staticmethod
    def get_interfaces():
        script = """
$items = Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
@($items) | ConvertTo-Json -Compress
"""
        data = NetworkManager._powershell_json(script)
        if data is None:
            return []
        if isinstance(data, str):
            return [data]
        return [str(x) for x in data if str(x).strip()]

    @staticmethod
    def get_all_active_configs():
        script = """
$result = foreach ($a in Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Where-Object {$_.Status -eq 'Up'}) {
$ipObj = Get-NetIPAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
Where-Object {$_.IPAddress -notlike '169.254.*'} | Select-Object -First 1
$gwObj = Get-NetRoute -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
Sort-Object RouteMetric | Select-Object -First 1
$ipIf = Get-NetIPInterface -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
[PSCustomObject]@{
interface = [string]$a.Name
description = [string]$a.InterfaceDescription
status = [string]$a.Status
ip = if ($ipObj) { [string]$ipObj.IPAddress } else { '' }
prefix = if ($ipObj) { [int]$ipObj.PrefixLength } else { $null }
gateway = if ($gwObj) { [string]$gwObj.NextHop } else { '' }
dhcp = if ($ipIf) { ([string]$ipIf.Dhcp -eq 'Enabled') } else { $false }
}
}
if ($null -eq $result) { @() | ConvertTo-Json -Compress } else { @($result) | ConvertTo-Json -Compress -Depth 4 }
"""
        data = NetworkManager._powershell_json(script)
        if data is None:
            return []
        if isinstance(data, dict):
            data = [data]
        active = []
        for item in data:
            if not isinstance(item, dict):
                continue
            prefix = item.get('prefix')
            mask = ''
            try:
                if prefix is not None:
                    mask = str(ipaddress.ip_network(f'0.0.0.0/{int(prefix)}').netmask)
            except (ValueError, TypeError):
                pass
            active.append({
                'interface': str(item.get('interface') or ''),
                'ip': str(item.get('ip') or ''),
                'mask': mask,
                'gateway': str(item.get('gateway') or ''),
                'dhcp': bool(item.get('dhcp', False)),
                'status': str(item.get('status') or ''),
            })
        return active

    @staticmethod
    def get_interface_config(interface):
        safe = interface.replace("'", "''")
        script = """
$Name = 'NAME'
$a = Get-NetAdapter -Name $Name -ErrorAction Stop
$ipObj = Get-NetIPAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {$_.IPAddress -notlike '169.254.*'} | Select-Object -First 1
$gwObj = Get-NetRoute -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Sort-Object RouteMetric | Select-Object -First 1
$ipIf = Get-NetIPInterface -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
[PSCustomObject]@{dhcp_enabled=if($ipIf){([string]$ipIf.Dhcp -eq 'Enabled')}else{$false}; ip=if($ipObj){[string]$ipObj.IPAddress}else{''}; mask=if($ipObj){[string]$ipObj.PrefixLength}else{''}; gateway=if($gwObj){[string]$gwObj.NextHop}else{''}} | ConvertTo-Json -Compress
""".replace('NAME', safe)
        data = NetworkManager._powershell_json(script)
        if not isinstance(data, dict):
            return None
        try:
            prefix = data.get('mask', '')
            mask = str(ipaddress.ip_network(f'0.0.0.0/{int(prefix)}').netmask) if prefix != '' else ''
        except (ValueError, TypeError):
            mask = ''
        return {'dhcp_enabled': bool(data.get('dhcp_enabled')), 'ip': data.get('ip') or '', 'mask': mask, 'gateway': data.get('gateway') or ''}

    @staticmethod
    def get_interface_state(interface):
        safe = interface.replace("'", "''")
        script = "$Name='__NAME__'; $a=Get-NetAdapter -Name $Name -ErrorAction Stop; [PSCustomObject]@{admin_state='Enabled';state=[string]$a.Status} | ConvertTo-Json -Compress".replace('__NAME__', safe)
        data = NetworkManager._powershell_json(script)
        if not isinstance(data, dict):
            return None
        return {'admin_state': str(data.get('admin_state', '')).lower(), 'state': str(data.get('state', '')).lower()}

    @staticmethod
    def apply_config(interface, ip, mask, gateway):
        try:
            if ip.upper() == 'DHCP':
                command = ['netsh', 'interface', 'ip', 'set', 'address', f'name={interface}', 'source=dhcp']
            elif gateway and gateway.upper() != 'DHCP':
                command = ['netsh', 'interface', 'ip', 'set', 'address', f'name={interface}', 'static', ip, mask, gateway, '1']
            else:
                command = ['netsh', 'interface', 'ip', 'set', 'address', f'name={interface}', 'static', ip, mask, 'none']
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW, check=False)
            if result.returncode == 0:
                return True, None
            error = result.stderr.decode('cp866', errors='replace').strip() or result.stdout.decode('cp866', errors='replace').strip()
            return False, error
        except Exception as e:
            return False, str(e)

    @staticmethod
    def set_interface_enabled(interface, enabled):
        try:
            command = ['netsh', 'interface', 'set', 'interface', interface, 'enable' if enabled else 'disable']
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW, check=False)
            if result.returncode == 0:
                return True, None
            error = result.stderr.decode('cp866', errors='replace').strip() or result.stdout.decode('cp866', errors='replace').strip()
            return False, error
        except Exception as e:
            return False, str(e)

    @staticmethod
    def ping_host(target):
        """Открывает отдельную консоль Windows и выполняет ping."""
        try:
            subprocess.Popen(
                ['cmd.exe', '/k', 'ping', '-n', '4', '-w', '1000', target],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            return True, None
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def run_ipconfig():
        """Открывает отдельную консоль Windows и выполняет ipconfig /all."""
        try:
            subprocess.Popen(
                ['cmd.exe', '/k', 'ipconfig', '/all'],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            return True, None
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def get_gateway_for_interface(interface):
        safe = interface.replace("'", "''")
        script = "$Name='__NAME__'; $a=Get-NetAdapter -Name $Name -ErrorAction SilentlyContinue; if($a){$r=Get-NetRoute -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Sort-Object RouteMetric | Select-Object -First 1; if($r){$r.NextHop}}".replace('__NAME__', safe)
        data = NetworkManager._powershell_json(script)
        if isinstance(data, str):
            return data.strip()
        return ''

    @staticmethod
    def check_subnet_overlap(interface, ip, mask):
        try:
            candidate = ipaddress.ip_network(f'{ip}/{mask}', strict=False)
        except ValueError:
            return False
        for item in NetworkManager.get_all_active_configs():
            if item.get('interface') == interface or not item.get('ip') or not item.get('mask'):
                continue
            try:
                network = ipaddress.ip_network(f"{item['ip']}/{item['mask']}", strict=False)
                if candidate.overlaps(network):
                    return True
            except ValueError:
                continue
        return False


class NetworkRefreshWorker(QtCore.QObject):
    """Получает сетевое состояние вне GUI-потока."""
    finished = QtCore.Signal(list, list)
    failed = QtCore.Signal(str)

    @QtCore.Slot()
    def run(self):
        try:
            interfaces = NetworkManager.get_interfaces()
            active = NetworkManager.get_all_active_configs()
            self.finished.emit(interfaces, active)
        except Exception as exc:
            self.failed.emit(str(exc))


class ConfigManager:
    """Класс для работы с файлом конфигураций"""

    def __init__(self, config_file=CONFIG_FILE):
        self.config_file = config_file

    def load(self):
        if not os.path.exists(self.config_file):
            return {'window_size': {}, 'configs': []}
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки: {e}")
            if os.path.exists(self.config_file):
                os.remove(self.config_file)
            return {'window_size': {}, 'configs': []}

    def save(self, data):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return True, None
        except Exception as e:
            return False, str(e)


class ActiveConfigWidget(QtWidgets.QFrame):
    """Карточка активного сетевого интерфейса."""
    gateway_ping_requested = QtCore.Signal(dict)
    create_config_requested = QtCore.Signal(dict)

    def __init__(self, config_data, parent=None):
        super().__init__(parent)
        self.config_data = config_data
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.init_ui()

    def show_context_menu(self, position):
        menu = QtWidgets.QMenu(self)
        ping_action = menu.addAction('Пинг шлюза')
        create_action = menu.addAction('Создать конфигурацию')
        gateway = str(self.config_data.get('gateway') or '').strip()
        ping_action.setEnabled(bool(gateway))
        action = menu.exec(self.mapToGlobal(position))
        if action == ping_action:
            self.gateway_ping_requested.emit(dict(self.config_data))
        elif action == create_action:
            self.create_config_requested.emit(dict(self.config_data))

    def init_ui(self):
        self.setFrameStyle(QtWidgets.QFrame.StyledPanel | QtWidgets.QFrame.Raised)
        self.setStyleSheet("""
            QFrame {
                background-color: #1F2937;
                border: 1px solid #374151;
                border-radius: 6px;
            }
            QFrame:hover {
                border: 1px solid #4B5563;
            }
        """)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 6, 10, 6)

        # Формируем текст IP
        if self.config_data['dhcp']:
            ip_text = "DHCP"
        else:
            ip_text = f"{self.config_data['ip']}"
            if self.config_data['mask']:
                try:
                    network = ipaddress.ip_network(f"0.0.0.0/{self.config_data['mask']}", strict=False)
                    cidr = network.prefixlen
                    ip_text = f"{self.config_data['ip']}/{cidr}"
                except Exception:
                    pass

        # Формируем текст шлюза
        gateway_text = self.config_data.get('gateway', '')

        # Создаём одну строку: Адаптер IP Шлюз
        if gateway_text:
            full_text = f"<b>{self.config_data['interface']}:</b> &nbsp; {ip_text} &nbsp; | &nbsp; {gateway_text}"
        else:
            full_text = f"<b>{self.config_data['interface']}</b> &nbsp; {ip_text}"

        info_label = QtWidgets.QLabel(full_text)
        info_label.setStyleSheet("color: #F9FAFB; font-size: 11px;")
        info_label.setTextFormat(QtCore.Qt.RichText)
        layout.addWidget(info_label)
        info_label.adjustSize()
        self.adjustSize()


class ConfigWidget(QtWidgets.QWidget):
    """Виджет одной сетевой конфигурации"""

    def __init__(self, config, main_window, parent=None):
        super().__init__(parent)
        self.config = config
        self.main_window = main_window
        self.network_manager = main_window.network_manager
        self.init_ui()
        self.update_status()

    def init_ui(self):
        self.setFixedSize(200, 150)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        self.header = QtWidgets.QLabel(self.config.get('name', 'Новая конфигурация'))
        self.header.setStyleSheet(self._get_style(COLOR_INACTIVE, COLOR_HEADER_BORDER))
        self.header.setAlignment(QtCore.Qt.AlignCenter)
        self.header.setFixedHeight(28)
        self.header.mouseDoubleClickEvent = self.apply_config
        self.header.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.header.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.header)

        self.interface_combo = QtWidgets.QComboBox()
        self.refresh_interfaces(self.main_window.interfaces_cache)
        self.interface_combo.currentIndexChanged.connect(self.update_status)
        layout.addWidget(self.interface_combo)

        self.ip_input = QtWidgets.QLineEdit(self.config.get('ip', ''))
        self.ip_input.setPlaceholderText('IP-адрес (x.x.x.x/xx)')
        self.ip_input.textChanged.connect(self.replace_commas)
        self.ip_input.editingFinished.connect(self.calculate_mask)
        self.ip_input.editingFinished.connect(self.update_status)
        layout.addWidget(self.ip_input)

        self.mask_input = QtWidgets.QLineEdit(self.config.get('mask', ''))
        self.mask_input.setPlaceholderText('Маска подсети (y.y.y.y)')
        self.mask_input.textChanged.connect(self.replace_commas)
        self.mask_input.editingFinished.connect(self.update_status)
        layout.addWidget(self.mask_input)

        self.gateway_input = QtWidgets.QLineEdit(self.config.get('gateway', ''))
        self.gateway_input.setPlaceholderText('Шлюз (необязательно)')
        self.gateway_input.textChanged.connect(self.replace_commas)
        self.gateway_input.editingFinished.connect(self.update_status)
        layout.addWidget(self.gateway_input)

    def refresh_interfaces(self, interfaces=None):
        """Обновить список интерфейсов, используя уже полученный список."""
        current_text = self.interface_combo.currentText()
        if interfaces is None:
            interfaces = self.network_manager.get_interfaces()
        self.interface_combo.blockSignals(True)
        self.interface_combo.clear()
        self.interface_combo.addItems(interfaces or [])
        wanted = current_text or self.config.get('interface', '')
        if wanted and wanted in (interfaces or []):
            self.interface_combo.setCurrentText(wanted)
        self.interface_combo.blockSignals(False)

    @staticmethod
    def _get_style(bg_color, border_color):
        return f"""
            background-color: {bg_color};
            color: black;
            border: 1px solid {border_color};
            border-radius: 3px;
            padding: 2px;
        """

    def replace_commas(self):
        """Заменяет разделители IPv4 без перемещения курсора ввода."""
        sender = self.sender()
        if not isinstance(sender, QtWidgets.QLineEdit):
            return
        text = sender.text()
        new_text = text.translate(str.maketrans({',': '.', 'ю': '.', 'Ю': '.'}))
        if new_text != text:
            cursor = sender.cursorPosition()
            sender.blockSignals(True)
            try:
                sender.setText(new_text)
                sender.setCursorPosition(cursor)
            finally:
                sender.blockSignals(False)

    def calculate_mask(self):
        ip_text = self.ip_input.text()
        if '/' in ip_text:
            try:
                ip_str, prefix_length = ip_text.split('/')
                network = ipaddress.ip_network(ip_text, strict=False)
                self.mask_input.setText(str(network.netmask))
                self.ip_input.setText(ip_str)
                gateway = str(network.network_address + 1)
                self.gateway_input.setText(gateway)
            except ValueError:
                QtWidgets.QMessageBox.warning(self, 'Ошибка', 'Неверный формат IP-адреса.')

    def apply_config(self, event=None):
        interface = self.interface_combo.currentText()
        ip = self.ip_input.text()
        mask = self.mask_input.text()
        gateway = self.gateway_input.text()

        if not interface:
            QtWidgets.QMessageBox.warning(self, 'Ошибка', 'Выберите интерфейс.')
            return

        if ip.upper() == 'DHCP':
            success, error = self.network_manager.apply_config(interface, ip, mask, gateway)
        else:
            if not all([ip, mask]):
                QtWidgets.QMessageBox.warning(self, 'Ошибка', 'Пожалуйста, заполните поля IP-адреса и маски или установите DHCP.')
                return
            if self.network_manager.check_subnet_overlap(interface, ip, mask):
                QtWidgets.QMessageBox.warning(self, 'Ошибка', 'Подсеть пересекается с другими интерфейсами.')
                return
            success, error = self.network_manager.apply_config(interface, ip, mask, gateway)

        if success:
            self.main_window.register_active_config(interface, self)
            self.main_window.refresh_network_state_async()
        else:
            QtWidgets.QMessageBox.warning(self, 'Ошибка', f'Не удалось применить конфигурацию.\n{error}')

    def show_context_menu(self, position):
        menu = QtWidgets.QMenu()
        edit_action = menu.addAction('Изменить')
        apply_action = menu.addAction('Применить')
        delete_action = menu.addAction('Удалить')
        clone_action = menu.addAction('Клонировать')
        menu.addSeparator()
        dhcp_action = menu.addAction('DHCP')
        ping_action = menu.addAction('Пинговать')
        menu.addSeparator()
        enable_action = menu.addAction('Включить')
        disable_action = menu.addAction('Отключить')

        action = menu.exec(self.header.mapToGlobal(position))

        if action == edit_action:
            self.edit_config()
        elif action == apply_action:
            self.apply_config()
        elif action == delete_action:
            self.confirm_delete()
        elif action == clone_action:
            self.clone_config()
        elif action == dhcp_action:
            self.set_dhcp()
        elif action == ping_action:
            self.ping()
        elif action == enable_action:
            self.enable_interface()
        elif action == disable_action:
            self.disable_interface()

    def confirm_delete(self):
        reply = QtWidgets.QMessageBox.question(
            self,
            'Подтверждение удаления',
            'Вы уверены, что хотите удалить эту конфигурацию?',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            interface = self.interface_combo.currentText()
            was_active = self.main_window.interface_to_active_config.get(interface) == self
            if was_active:
                self.main_window.interface_to_active_config.pop(interface, None)
            self.deleteLater()
            QtCore.QTimer.singleShot(50, lambda: self.main_window.rebuild_layout())
            self.main_window.save_configurations()
            if was_active:
                self.main_window.update_all_statuses()

    def clone_config(self):
        cloned_config = self.get_config().copy()
        base_name = cloned_config.get('name', 'Новая конфигурация')
        clone_name = base_name + ' (Клон)'
        existing_names = [w.header.text() for w in self.main_window.get_all_config_widgets()]
        count = 1
        while clone_name in existing_names:
            clone_name = f"{base_name} (Клон {count})"
            count += 1
        cloned_config['name'] = clone_name

        clone = ConfigWidget(cloned_config, self.main_window, parent=self.parent())
        self.main_window.add_config_widget(clone)
        self.main_window.save_configurations()

    def set_dhcp(self):
        self.ip_input.setText('DHCP')
        self.mask_input.setText('DHCP')
        self.gateway_input.setText('DHCP')
        self.main_window.save_configurations()
        self.update_status()

    def ping(self):
        ip = self.ip_input.text()
        gateway = self.gateway_input.text()
        interface = self.interface_combo.currentText()

        target = None
        if gateway and gateway.upper() != 'DHCP':
            target = gateway
        elif interface:
            target = self.network_manager.get_gateway_for_interface(interface)

        if not target:
            target = ip if ip and ip.upper() != 'DHCP' else None

        if not target:
            QtWidgets.QMessageBox.warning(self, 'Ошибка', 'Нет адреса для пинга. Укажите шлюз или IP-адрес.')
            return

        success, error = self.network_manager.ping_host(target)
        if not success:
            QtWidgets.QMessageBox.warning(self, 'Ошибка', f'Не удалось выполнить команду пинга.\n{error}')

    def enable_interface(self):
        interface = self.interface_combo.currentText()
        if not interface:
            return

        success, error = self.network_manager.set_interface_enabled(interface, True)
        if success:
            self.main_window.refresh_network_state_async()
        else:
            QtWidgets.QMessageBox.warning(self, 'Ошибка', f'Не удалось включить интерфейс.\n{error}')

    def disable_interface(self):
        interface = self.interface_combo.currentText()
        if not interface:
            return

        success, error = self.network_manager.set_interface_enabled(interface, False)
        if success:
            self.main_window.refresh_network_state_async()
        else:
            QtWidgets.QMessageBox.warning(self, 'Ошибка', f'Не удалось отключить интерфейс.\n{error}')

    def edit_config(self):
        name, ok = QtWidgets.QInputDialog.getText(
            self,
            'Изменить имя',
            'Введите новое имя:',
            text=self.header.text()
        )
        if ok:
            self.header.setText(name)
            self.config['name'] = name
            self.main_window.save_configurations()

    def get_config(self):
        self.config['name'] = self.header.text()
        self.config['interface'] = self.interface_combo.currentText()
        self.config['ip'] = self.ip_input.text()
        self.config['mask'] = self.mask_input.text()
        self.config['gateway'] = self.gateway_input.text()
        return self.config

    def set_active(self):
        self.header.setStyleSheet(self._get_style(COLOR_ACTIVE, COLOR_ACTIVE_BORDER))

    def set_inactive(self):
        self.header.setStyleSheet(self._get_style(COLOR_INACTIVE, COLOR_HEADER_BORDER))

    def set_error(self):
        self.header.setStyleSheet(self._get_style(COLOR_ERROR, COLOR_ERROR_BORDER))

    def update_status(self):
        """Обновляет статус карточки из кэша без запуска PowerShell."""
        interface = self.interface_combo.currentText()
        if not interface:
            return

        config = self.main_window.network_snapshot.get(interface)
        if not config:
            self.set_inactive()
            return

        ip_matches = False
        configured_ip = self.ip_input.text().strip()
        configured_mask = self.mask_input.text().strip()
        configured_gateway = self.gateway_input.text().strip()

        if config.get('dhcp') and configured_ip.upper() == 'DHCP':
            ip_matches = True
        elif not config.get('dhcp'):
            ip_matches = (
                config.get('ip', '') == configured_ip and
                config.get('mask', '') == configured_mask and
                (config.get('gateway', '') == configured_gateway or
                 (not config.get('gateway', '') and not configured_gateway))
            )

        # Get-NetAdapter возвращает статус Up независимо от языка Windows.
        connected = str(config.get('status', '')).lower() == 'up'

        if ip_matches and connected:
            self.main_window.register_active_config(interface, self)
        elif connected:
            self.set_error()
        else:
            self.set_inactive()


class MainWindow(QtWidgets.QMainWindow):
    """Главное окно приложения"""

    def __init__(self):
        super().__init__()
        self.interface_to_active_config = {}
        self.config_manager = ConfigManager()
        self.network_manager = NetworkManager()
        self.interfaces_cache = []
        self.network_snapshot = {}
        self._refresh_thread = None
        self._refresh_worker = None
        self._last_grid_columns = None
        self.init_ui()
        self.load_configurations()
        QtCore.QTimer.singleShot(100, self.refresh_network_state_async)

    def init_ui(self):
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(700, 500)

        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.create_menu_bar()

        self.active_configs_group = QtWidgets.QGroupBox("Активные сетевые конфигурации")
        self.active_configs_layout = QtWidgets.QGridLayout()
        self.active_configs_layout.setSpacing(8)
        self.active_configs_layout.setContentsMargins(8, 8, 8, 8)
        self.active_configs_layout.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.active_configs_group.setLayout(self.active_configs_layout)
        main_layout.addWidget(self.active_configs_group)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.scroll_content = QtWidgets.QWidget()
        self.scroll_layout = QtWidgets.QGridLayout(self.scroll_content)
        self.scroll_layout.setSpacing(10)
        self.scroll_layout.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)

        self.scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll_area)

        self.add_button = QtWidgets.QPushButton('+ Добавить конфигурацию')
        self.add_button.setMinimumHeight(35)
        self.add_button.clicked.connect(self.add_configuration)
        main_layout.addWidget(self.add_button)

        self.update_active_configs_display()

    def create_menu_bar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu('Файл')

        new_action = QtGui.QAction('Новый', self)
        new_action.setShortcut('Ctrl+N')
        new_action.triggered.connect(self.new_configuration)
        file_menu.addAction(new_action)

        open_action = QtGui.QAction('Открыть...', self)
        open_action.setShortcut('Ctrl+O')
        open_action.triggered.connect(self.open_configurations)
        file_menu.addAction(open_action)

        save_action = QtGui.QAction('Сохранить', self)
        save_action.setShortcut('Ctrl+S')
        save_action.triggered.connect(self.save_configurations)
        file_menu.addAction(save_action)

        save_as_action = QtGui.QAction('Сохранить как...', self)
        save_as_action.setShortcut('Ctrl+Shift+S')
        save_as_action.triggered.connect(self.save_configurations_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        exit_action = QtGui.QAction('Выход', self)
        exit_action.setShortcut('Alt+F4')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        network_menu = menu_bar.addMenu('Сеть')

        refresh_action = QtGui.QAction('⟳ Обновить интерфейсы', self)
        refresh_action.setShortcut('F5')
        refresh_action.triggered.connect(self.refresh_all_interfaces)
        network_menu.addAction(refresh_action)

        self.ping_menu = network_menu.addMenu('Пинг')
        self.ping_menu.aboutToShow.connect(self.populate_ping_menu)

        masks_action = QtGui.QAction('Маски', self)
        masks_action.triggered.connect(self.show_masks)
        network_menu.addAction(masks_action)


        ipconfig_action = QtGui.QAction('IPConfig', self)
        ipconfig_action.setShortcut('Ctrl+I')
        ipconfig_action.triggered.connect(self.show_ipconfig)
        network_menu.addAction(ipconfig_action)

        help_menu = menu_bar.addMenu('Справка')

        help_content_action = QtGui.QAction('Содержание справки', self)
        help_content_action.setShortcut('F1')
        help_content_action.triggered.connect(self.show_help)
        help_menu.addAction(help_content_action)

        about_action = QtGui.QAction('О программе', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def refresh_all_interfaces(self):
        """Запускает обновление сети в фоне, не блокируя интерфейс."""
        self.refresh_network_state_async()

    def refresh_network_state_async(self):
        if self._refresh_thread is not None and self._refresh_thread.isRunning():
            return
        self.statusBar().showMessage('Обновление адаптеров...')
        self._refresh_thread = QtCore.QThread(self)
        self._refresh_worker = NetworkRefreshWorker()
        self._refresh_worker.moveToThread(self._refresh_thread)
        self._refresh_thread.started.connect(self._refresh_worker.run)
        self._refresh_worker.finished.connect(self._on_network_refresh_finished)
        self._refresh_worker.failed.connect(self._on_network_refresh_failed)
        self._refresh_worker.finished.connect(self._refresh_thread.quit)
        self._refresh_worker.failed.connect(self._refresh_thread.quit)
        self._refresh_thread.finished.connect(self._refresh_thread.deleteLater)
        self._refresh_thread.finished.connect(self._clear_refresh_worker)
        self._refresh_thread.start()

    @QtCore.Slot(list, list)
    def _on_network_refresh_finished(self, interfaces, active_configs):
        self.interfaces_cache = list(interfaces or [])
        self.network_snapshot = {item.get('interface'): item for item in (active_configs or []) if item.get('interface')}
        for widget in self.get_all_config_widgets():
            widget.refresh_interfaces(self.interfaces_cache)
            widget.update_status()
        self._render_active_configs(active_configs)
        self.statusBar().showMessage('Адаптеры обновлены', 2000)

    @QtCore.Slot(str)
    def _on_network_refresh_failed(self, error):
        self.statusBar().showMessage('Не удалось обновить адаптеры', 3000)
        print(f'Ошибка обновления сети: {error}')

    @QtCore.Slot()
    def _clear_refresh_worker(self):
        self._refresh_worker = None
        self._refresh_thread = None

    def ping_gateway(self):
        """Пинг всех найденных шлюзов через отдельные окна CMD."""
        gateways = []
        for item in self.network_snapshot.values():
            gateway = str(item.get('gateway') or '').strip()
            if gateway and gateway not in gateways:
                gateways.append(gateway)
        if not gateways:
            QtWidgets.QMessageBox.information(self, 'Пинг шлюза', 'У активных интерфейсов не найдено ни одного шлюза.')
            return
        for gateway in gateways:
            self._ping_gateway_in_console(gateway)

    def populate_ping_menu(self):
        """Заполняет меню «Сеть -> Пинг» текущими активными интерфейсами."""
        if not hasattr(self, "ping_menu"):
            return
        self.ping_menu.clear()
        active_configs = list(getattr(self, "network_snapshot", {}).values())
        if not active_configs:
            action = self.ping_menu.addAction("Нет активных интерфейсов")
            action.setEnabled(False)
            return
        added = False
        for config in active_configs:
            interface = str(config.get("interface") or "").strip()
            gateway = str(config.get("gateway") or "").strip()
            if not interface:
                continue
            if gateway:
                action = self.ping_menu.addAction(f"{interface} — {gateway}")
                action.setData(gateway)
                action.triggered.connect(self.ping_selected_gateway)
                added = True
            else:
                action = self.ping_menu.addAction(f"{interface} — шлюз не найден")
                action.setEnabled(False)
        if not added:
            action = self.ping_menu.addAction("У активных интерфейсов нет шлюзов")
            action.setEnabled(False)

    def ping_selected_gateway(self):
        """Обрабатывает выбор шлюза из меню «Сеть -> Пинг»."""
        action = self.sender()
        if not isinstance(action, QtGui.QAction):
            return
        gateway = str(action.data() or "").strip()
        if gateway:
            self._ping_gateway_in_console(gateway)

    def _ping_gateway_in_console(self, gateway):
        """Запускает ping шлюза в отдельном окне Windows CMD."""
        gateway = str(gateway or "").strip()
        if not gateway:
            return
        try:
            subprocess.Popen(
                ["cmd.exe", "/k", "ping", "-n", "4", "-w", "1000", gateway],
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Ошибка", f"Не удалось запустить ping шлюза {gateway}.\n{e}"
            )

    def ping_active_gateway(self, config_data):
        """ПКМ по активному интерфейсу -> Пинг шлюза."""
        config_data = config_data or {}
        gateway = str(config_data.get("gateway") or "").strip()
        interface = str(config_data.get("interface") or "").strip()
        if not gateway and interface:
            try:
                gateway = str(self.network_manager.get_gateway_for_interface(interface) or "").strip()
            except Exception:
                gateway = ""
        if not gateway:
            QtWidgets.QMessageBox.information(self, "Пинг шлюза", f"Для интерфейса «{interface}» шлюз не найден.")
            return
        self._ping_gateway_in_console(gateway)

    def create_configuration_from_active(self, config_data):
        """ПКМ по активному интерфейсу -> Создать конфигурацию."""
        config_data = config_data or {}
        interface = str(config_data.get("interface") or "").strip()
        if not interface:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Не удалось определить сетевой интерфейс.")
            return
        if bool(config_data.get("dhcp")):
            ip = "DHCP"
            mask = "DHCP"
            gateway = "DHCP"
        else:
            ip = str(config_data.get("ip") or "").strip()
            mask = str(config_data.get("mask") or "").strip()
            gateway = str(config_data.get("gateway") or "").strip()

        existing_names = set()
        for i in range(self.scroll_layout.count()):
            item = self.scroll_layout.itemAt(i)
            widget = item.widget()
            if not isinstance(widget, ConfigWidget):
                continue
            try:
                config = widget.get_config()
                if isinstance(config, dict):
                    name = str(config.get("name") or "").strip()
                    if name:
                        existing_names.add(name)
            except Exception:
                pass

        name = interface
        counter = 1
        while name in existing_names:
            name = f"{interface} ({counter})"
            counter += 1

        config = {
            "name": name,
            "interface": interface,
            "ip": ip,
            "mask": mask,
            "gateway": gateway,
        }
        try:
            widget = ConfigWidget(config, self, parent=self.scroll_content)
            self.add_config_widget(widget)
            if hasattr(self, "rebuild_layout"):
                self.rebuild_layout()
            self.save_configurations()
            self.statusBar().showMessage(f"Создана конфигурация «{name}» из активного интерфейса", 3000)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Ошибка", f"Не удалось создать конфигурацию.\n{e}")

    def show_ipconfig(self):
        success, error = self.network_manager.run_ipconfig()
        if not success:
            QtWidgets.QMessageBox.warning(self, 'Ошибка', f'Не удалось выполнить ipconfig.\n{error}')

    def new_configuration(self):
        widgets = self.get_all_config_widgets()
        for widget in widgets:
            widget.deleteLater()
        self.interface_to_active_config.clear()
        QtCore.QTimer.singleShot(50, lambda: self.add_configuration())

    def open_configurations(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Открыть конфигурации', '', 'JSON Files (*.json);;All Files (*)'
        )
        if file_path:
            self.config_manager.config_file = file_path
            self.load_configurations()

    def save_configurations_as(self):
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Сохранить конфигурации как', '', 'JSON Files (*.json);;All Files (*)'
        )
        if file_path:
            self.config_manager.config_file = file_path
            self.save_configurations()

    def show_help(self):
        QtWidgets.QMessageBox.information(
            self, 'Справка',
            'IPChanger - программа для управления сетевыми конфигурациями.\n\n'
            'Использование:\n'
            '- Двойной клик по заголовку конфигурации - применить\n'
            '- Правый клик - контекстное меню\n'
            '- F5 или меню "Сеть" - обновить интерфейсы\n'
            '- Меню "Сеть" - пинг шлюза и ipconfig\n'
            '- Ctrl+S - сохранить конфигурации\n'
            '- Ctrl+N - новая конфигурация'
        )

    def show_about(self):
        QtWidgets.QMessageBox.about(
            self, 'О программе',
            f'Разработчик: MrBorodaX\n'
            f'{APP_NAME} v{APP_VERSION}\n'
            f'Дата обновления: {DATE}\n'
            f'\n'
            f'Copyright © 2026 MrBorodaX.\n'
            f'This program is free software: you can redistribute it and/or modify it \n'
            f'under the terms of the GNU General Public License as published by the \n'
            f'Free Software Foundation, either version 3 of the License, or (at your \n'
            f'option) any later version.'
        )

    def show_masks(self):
        """Показать таблицу масок подсети в красивом виде."""
        masks = [
            ('255.255.255.255', '/32', '1'),
            ('255.255.255.254', '/31', '2'),
            ('255.255.255.252', '/30', '2'),
            ('255.255.255.248', '/29', '6'),
            ('255.255.255.240', '/28', '14'),
            ('255.255.255.224', '/27', '30'),
            ('255.255.255.192', '/26', '62'),
            ('255.255.255.128', '/25', '126'),
            ('255.255.255.0', '/24', '254'),
            ('255.255.254.0', '/23', '510'),
            ('255.255.252.0', '/22', '1 022'),
            ('255.255.248.0', '/21', '2 046'),
            ('255.255.240.0', '/20', '4 094'),
            ('255.255.224.0', '/19', '8 190'),
            ('255.255.192.0', '/18', '16 382'),
            ('255.255.128.0', '/17', '32 766'),
            ('255.255.0.0', '/16', '65 534'),
            ('255.254.0.0', '/15', '131 070'),
            ('255.252.0.0', '/14', '262 142'),
            ('255.248.0.0', '/13', '524 286'),
            ('255.240.0.0', '/12', '1 048 574'),
            ('255.224.0.0', '/11', '2 097 150'),
            ('255.192.0.0', '/10', '4 194 302'),
            ('255.128.0.0', '/9', '8 388 606'),
            ('255.0.0.0', '/8', '16 777 214'),
        ]

        # Создаём диалоговое окно
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle('Маски подсети IPv4')
        dialog.setMinimumSize(500, 600)
        dialog.setModal(True)

        layout = QtWidgets.QVBoxLayout(dialog)

        # Заголовок
        title = QtWidgets.QLabel('Таблица масок подсети IPv4')
        title.setStyleSheet("font-size: 14px; font-weight: bold; padding: 10px;")
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)

        # Создаём таблицу
        table = QtWidgets.QTableWidget()
        table.setRowCount(len(masks))
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(['Маска подсети', 'CIDR', 'Хостов'])

        # Настройка таблицы
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)

        # В некоторых темах Windows AlternateBase остаётся белым даже при
        # тёмном Base. Поэтому не используем его напрямую.
        palette = dialog.palette()
        base = palette.color(QtGui.QPalette.ColorRole.Base)
        # Если Base и Window расходятся по яркости, ориентируемся на фон окна.
        window = palette.color(QtGui.QPalette.ColorRole.Window)
        if (base.lightness() < 128) != (window.lightness() < 128):
            base = window
        dark_theme = base.lightness() < 128
        alternate = base.lighter(115) if dark_theme else base.darker(106)
        text_color = QtGui.QColor('#FFFFFF') if dark_theme else QtGui.QColor('#111111')
        window_text = text_color
        highlight = palette.color(QtGui.QPalette.ColorRole.Highlight)
        highlighted_text = palette.color(QtGui.QPalette.ColorRole.HighlightedText)
        border = palette.color(QtGui.QPalette.ColorRole.Mid)

        def css_color(color):
            return color.name(QtGui.QColor.NameFormat.HexRgb)

        table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {css_color(base)};
                alternate-background-color: {css_color(alternate)};
                color: {css_color(text_color)};
                border: 1px solid {css_color(border)};
                gridline-color: {css_color(border)};
                font-size: 11px;
            }}
            QTableWidget::item {{ padding: 5px; }}
            QTableWidget::item:selected {{
                background-color: {css_color(highlight)};
                color: {css_color(highlighted_text)};
            }}
            QHeaderView::section {{
                background-color: {css_color(window)};
                color: {css_color(window_text)};
                padding: 8px;
                border: 1px solid {css_color(border)};
                font-weight: bold;
                font-size: 12px;
            }}
        """)

        table_palette = table.palette()
        table_palette.setColor(QtGui.QPalette.ColorRole.Base, base)
        table_palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, alternate)
        table_palette.setColor(QtGui.QPalette.ColorRole.Text, text_color)
        table.setPalette(table_palette)

        # Заполняем таблицу
        for row, (mask, cidr, hosts) in enumerate(masks):
            table.setItem(row, 0, QtWidgets.QTableWidgetItem(mask))
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(cidr))
            table.setItem(row, 2, QtWidgets.QTableWidgetItem(hosts))

        # Выравнивание по центру для CIDR и Хостов
        for row in range(len(masks)):
            for col in [1, 2]:
                item = table.item(row, col)
                if item:
                    item.setTextAlignment(QtCore.Qt.AlignCenter)

        layout.addWidget(table)

        # Кнопка закрытия
        close_button = QtWidgets.QPushButton('Закрыть')
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2563EB;
            }
        """)
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, alignment=QtCore.Qt.AlignCenter)

        dialog.exec()

    def add_configuration(self):
        config_widget = ConfigWidget({}, self, parent=self.scroll_content)
        self.add_config_widget(config_widget)
        self.save_configurations()

    def add_config_widget(self, widget):
        row, col = self.get_next_grid_position()
        self.scroll_layout.addWidget(widget, row, col)
        widget.show()

    def rebuild_layout(self):
        widgets = self.get_all_config_widgets()
        for i in range(self.scroll_layout.count() - 1, -1, -1):
            item = self.scroll_layout.itemAt(i)
            if item is not None:
                w = item.widget()
                if w is not None:
                    self.scroll_layout.removeWidget(w)
        for idx, widget in enumerate(widgets):
            columns = self.get_columns_count()
            row = idx // columns
            col = idx % columns
            self.scroll_layout.addWidget(widget, row, col)

    def get_columns_count(self):
        width = self.scroll_area.width()
        widget_width = 200 + 10
        columns = max(1, width // widget_width)
        return columns

    def get_next_grid_position(self):
        count = len(self.get_all_config_widgets())
        columns = self.get_columns_count()
        row = count // columns
        col = count % columns
        return row, col

    def load_configurations(self):
        data = self.config_manager.load()
        window_size = data.get('window_size', {})
        if 'width' in window_size and 'height' in window_size:
            self.resize(window_size['width'], window_size['height'])
        configs = data.get('configs', [])
        for config in configs:
            config_widget = ConfigWidget(config, self, parent=self.scroll_content)
            self.add_config_widget(config_widget)
        self.update_active_configs_display()

    def save_configurations(self):
        configs = []
        for widget in self.get_all_config_widgets():
            configs.append(widget.get_config())
        window_size = {"width": self.width(), "height": self.height()}
        data = {"window_size": window_size, "configs": configs}
        success, error = self.config_manager.save(data)
        if not success:
            QtWidgets.QMessageBox.warning(self, 'Ошибка', f'Не удалось сохранить конфигурации.\n{error}')

    def update_active_configs_display(self):
        """Отрисовывает уже полученные активные подключения."""
        self._render_active_configs(list(self.network_snapshot.values()))

    def _render_active_configs(self, active_configs):
        while self.active_configs_layout.count():
            item = self.active_configs_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not active_configs:
            label = QtWidgets.QLabel("Нет активных сетевых подключений")
            label.setStyleSheet("color: #9CA3AF; font-style: italic; padding: 5px;")
            self.active_configs_layout.addWidget(label, 0, 0)
            return
        available = max(220, self.active_configs_group.width() - 20)
        card_widths = []
        for config_data in active_configs:
            probe = ActiveConfigWidget(config_data)
            probe.adjustSize()
            card_widths.append(max(160, probe.sizeHint().width()))
            probe.deleteLater()
        card_width = max(card_widths or [220])
        columns = max(1, available // card_width)
        for i, config_data in enumerate(active_configs):
            widget = ActiveConfigWidget(config_data)
            widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Fixed)
            widget.adjustSize()
            widget.gateway_ping_requested.connect(self.ping_active_gateway)
            widget.create_config_requested.connect(self.create_configuration_from_active)
            self.active_configs_layout.addWidget(widget, i // columns, i % columns)
        for col in range(columns):
            self.active_configs_layout.setColumnStretch(col, 0)

    def update_all_statuses(self):
        for widget in self.get_all_config_widgets():
            widget.update_status()
        self.update_active_configs_display()

    def register_active_config(self, interface, config_widget):
        if interface in self.interface_to_active_config:
            previous_config = self.interface_to_active_config[interface]
            if previous_config != config_widget:
                previous_config.set_inactive()
        self.interface_to_active_config[interface] = config_widget
        config_widget.set_active()

    def get_all_config_widgets(self):
        widgets = []
        for i in range(self.scroll_layout.count()):
            item = self.scroll_layout.itemAt(i)
            if item is not None:
                widget = item.widget()
                if isinstance(widget, ConfigWidget):
                    widgets.append(widget)
        return widgets

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QtCore.QTimer.singleShot(50, self.rebuild_layout)
        QtCore.QTimer.singleShot(50, self.update_active_configs_display)

    def closeEvent(self, event):
        self.save_configurations()
        event.accept()


def main():
    import traceback
    import ctypes
    import os
    from PySide6 import QtGui

    # ВАЖНО: SetCurrentProcessExplicitAppUserModelID должен быть ДО QApplication
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("IPChanger.App.1")
    except Exception as e:
        print(f"Не удалось установить AppUserModelID: {e}")

    try:
        app = QtWidgets.QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setApplicationVersion(APP_VERSION)

        # Абсолютный путь к иконке
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.ico')
        if not os.path.exists(icon_path):
            print(f"Внимание: файл иконки не найден по пути {icon_path}")
        else:
            print(f"Иконка найдена: {icon_path}")

        # Устанавливаем иконку на приложение
        app_icon = QtGui.QIcon(icon_path)
        app.setWindowIcon(app_icon)

        if not is_admin():
            reply = QtWidgets.QMessageBox.warning(
                None,
                'Внимание',
                'Приложение запущено без прав администратора.\n'
                'Некоторые функции (применение конфигурации, включение/отключение интерфейсов) '
                'могут не работать.\n\n'
                'Рекомендуется запустить программу от имени администратора.\n\n'
                'Продолжить работу?',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )
            if reply == QtWidgets.QMessageBox.No:
                sys.exit(0)

        window = MainWindow()

        # ВАЖНО: устанавливаем иконку и на само окно
        window.setWindowIcon(app_icon)
        window.show()

        sys.exit(app.exec())
    except Exception as e:
        print("Произошла ошибка при запуске программы:")
        print(e)
        traceback.print_exc()
        QtWidgets.QMessageBox.critical(
            None,
            'Критическая ошибка',
            f'Произошла ошибка при запуске программы:\n{e}'
        )
        sys.exit(1)


if __name__ == '__main__':
    main()