"""Program Files installs must keep normal runtime writes out of the app folder."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import common
import installer
import app


class InstallLocationTests(unittest.TestCase):
    def test_uninstalled_build_copy_reopens_verified_registered_app(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            installation, data, copy = (base / name for name in ('App', 'Data', 'assets'))
            installation.mkdir(); data.mkdir(); copy.mkdir()
            target = installation / common.APP_EXE
            target.write_bytes(b'installed')
            common.atomic_json(installation / 'studio-install.json', {'app': common.APP_NAME})
            common.atomic_json(data / 'studio-data.json', {'app': common.APP_NAME})
            with patch.object(sys, 'frozen', True, create=True), \
                    patch.object(sys, 'executable', str(copy / common.APP_EXE)), \
                    patch('common.registered_installation', return_value=(installation, data)):
                self.assertEqual(common.installed_app_for_copy(), target.resolve())
                self.assertEqual(list(copy.iterdir()), [])
                common.atomic_json(data / 'studio-data.json', {'app': 'unrelated'})
                self.assertIsNone(common.installed_app_for_copy())
                common.atomic_json(data / 'studio-data.json', {'app': common.APP_NAME})
                target.unlink()
                self.assertIsNone(common.installed_app_for_copy())

    def test_portable_data_and_source_runs_never_redirect(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(sys, 'frozen', True, create=True), \
                    patch.object(sys, 'executable', str(root / common.APP_EXE)), \
                    patch('common.registered_installation') as registered:
                for name in ('studio-install.json','studio-data.json','settings.json','runtime-ready.json'):
                    file = root / name
                    file.write_text('{}')
                    self.assertIsNone(common.installed_app_for_copy())
                    file.unlink()
                registered.assert_not_called()
            with patch.object(sys, 'frozen', False, create=True):
                self.assertIsNone(common.installed_app_for_copy())

    def test_redirect_preserves_launch_flags_and_explicit_root_bypasses_it(self):
        target = Path('I:/Studio') / common.APP_EXE
        with patch.object(sys, 'argv', ['studio.exe','--headless']), \
                patch('app.installed_app_for_copy', return_value=target), \
                patch('app.subprocess.Popen') as launch, patch('app.Studio') as studio:
            app.main()
            launch.assert_called_once_with([str(target),'--headless'], cwd=target.parent,
                                           creationflags=common.CREATE_NO_WINDOW)
            studio.assert_not_called()
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(sys, 'argv', ['studio.exe','--root',folder,'--headless']), \
                patch('app.installed_app_for_copy') as redirect, \
                patch('app.Studio', side_effect=RuntimeError('explicit test profile')):
            with self.assertRaisesRegex(RuntimeError, 'explicit test profile'):
                app.main()
            redirect.assert_not_called()

    def test_program_files_default_does_not_follow_previous_install(self):
        with patch.dict(common.os.environ, {'ProgramW6432': 'C:/Program Files'}), \
                patch('common.registered_installation', return_value=(Path('I:/OldStudio'), Path('I:/OldStudio'))):
            self.assertEqual(common.default_install_path(), Path('C:/Program Files/AI Image & Video Studio'))

    def test_new_program_files_install_uses_writable_user_data(self):
        with patch('common.registered_installation', return_value=(None, None)):
            data = common.default_data_path(common.default_install_path())
            self.assertEqual(data, common.local_data_path())
            self.assertFalse(common.in_program_files(data))

    def test_existing_models_can_be_reused_without_moving_them(self):
        with tempfile.TemporaryDirectory() as folder:
            previous = Path(folder).resolve()
            with patch('common.registered_installation', return_value=(previous, previous)):
                self.assertEqual(common.default_data_path(common.default_install_path()), previous)
                # Uninstalling a different app location must not select these shared files.
                self.assertEqual(common.installed_data_path(common.default_install_path()), common.local_data_path())

    def test_frozen_app_selects_registered_data_and_keeps_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root, data = Path(folder) / 'App', Path(folder) / 'Models'
            with patch.object(sys, 'frozen', True, create=True), \
                    patch.object(sys, 'executable', str(root / common.APP_EXE)), \
                    patch('common.registered_installation', return_value=(root.resolve(), data.resolve())):
                self.assertEqual(common.app_root(), data.resolve())
            with patch('common.registered_installation', return_value=(None, None)):
                self.assertEqual(common.installed_data_path(root), root.resolve())

    def test_data_cannot_live_under_program_files_or_replace_unrelated_files(self):
        with self.assertRaises(ValueError):
            common.check_data_path(common.default_install_path() / 'Models')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'personal.txt').write_text('keep me')
            with self.assertRaises(ValueError):
                common.check_data_path(root)
            common.atomic_json(root / 'studio-data.json', {'app': common.APP_NAME})
            self.assertEqual(common.check_data_path(root), root.resolve())

    def test_upgrade_preserves_data_when_app_and_models_are_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            root, data, bundle = (Path(folder) / name for name in ('App', 'Data', 'Bundle'))
            data.mkdir(); bundle.mkdir()
            common.atomic_json(data / 'studio-data.json', {'app': common.APP_NAME})
            files = {'settings.json': b'{"prompt":"keep this"}', 'library.json': b'[]', 'images.json': b'[]'}
            for name, content in files.items():
                (data / name).write_bytes(content)
            (bundle / common.APP_EXE).write_bytes(b'test bundled app')
            with patch('installer.resource', side_effect=lambda name: bundle / name), \
                    patch('installer.ensure_desktop_runtime'), patch('installer.register_uninstall') as register:
                self.assertEqual(installer.install_application(root, False, False, data), root.resolve())
                register.assert_called_once_with(root.resolve(), data.resolve())
            self.assertEqual((root / common.APP_EXE).read_bytes(), b'test bundled app')
            self.assertFalse((root / 'settings.json').exists())
            for name, content in files.items():
                self.assertEqual((data / name).read_bytes(), content)

    def test_rejected_elevation_leaves_personal_data_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder) / 'Data'
            with patch('installer.elevated_application_action', side_effect=RuntimeError('Approval cancelled')), \
                    self.assertRaisesRegex(RuntimeError, 'Approval cancelled'):
                installer.install_application(common.default_install_path(), False, False, data)
            self.assertFalse(data.exists())


if __name__ == '__main__':
    unittest.main()
