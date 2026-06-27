using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Office.Interop.Word;

namespace WordAI
{
    public class HotkeyManager : NativeWindow, IDisposable
    {
        private const int WM_HOTKEY = 0x0312;
        private const int MOD_CONTROL = 0x0002;
        private const int VK_E = 0x45;
        private const int VK_RETURN = 0x0D;

        [DllImport("user32.dll")]
        private static extern bool RegisterHotKey(IntPtr hWnd, int id, int fsModifiers, int vk);

        [DllImport("user32.dll")]
        private static extern bool UnregisterHotKey(IntPtr hWnd, int id);

        private readonly ThisAddIn _addin;
        private bool _isContinueActive;
        private string _continueSessionId;
        private CancellationTokenSource _continueCts;

        private const int HOTKEY_POLISH = 1;
        private const int HOTKEY_CONTINUE = 2;

        public HotkeyManager(ThisAddIn addin)
        {
            _addin = addin;
        }

        public void Register()
        {
            // 获取 Word 主窗口句柄
            IntPtr hWnd = new IntPtr(_addin.Application.ActiveWindow.Hwnd);
            this.AssignHandle(hWnd);

            RegisterHotKey(this.Handle, HOTKEY_POLISH, MOD_CONTROL, VK_E);
            RegisterHotKey(this.Handle, HOTKEY_CONTINUE, MOD_CONTROL, VK_RETURN);
        }

        public void Unregister()
        {
            UnregisterHotKey(this.Handle, HOTKEY_POLISH);
            UnregisterHotKey(this.Handle, HOTKEY_CONTINUE);
            this.ReleaseHandle();
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == WM_HOTKEY)
            {
                int id = m.WParam.ToInt32();
                switch (id)
                {
                    case HOTKEY_POLISH:
                        if (!_isContinueActive)
                            HandlePolish();
                        break;
                    case HOTKEY_CONTINUE:
                        HandleContinueToggle();
                        break;
                }
            }
            base.WndProc(ref m);
        }

        private async void HandlePolish()
        {
            try
            {
                string selectedText = _addin.ContextExtractor.GetSelectedText();
                if (string.IsNullOrWhiteSpace(selectedText))
                {
                    _addin.Application.StatusBar = "WordAI: 请先选中文本再润色";
                    return;
                }

                _addin.Application.StatusBar = "WordAI: 正在润色...";
                string polished = await _addin.BackendClient.PolishAsync(selectedText);
                _addin.TextWriter.ReplaceSelection(polished);
                _addin.Application.StatusBar = "WordAI: 润色完成";
            }
            catch (Exception ex)
            {
                _addin.Application.StatusBar = $"WordAI: 润色失败 - {ex.Message}";
            }
        }

        private async void HandleContinueToggle()
        {
            if (_isContinueActive)
            {
                // 停止续写
                _isContinueActive = false;
                _continueCts?.Cancel();
                string finalText = await _addin.BackendClient.StopAsync(_continueSessionId);
                if (!string.IsNullOrEmpty(finalText))
                {
                    _addin.TextWriter.InsertText(finalText);
                }
                _addin.Application.StatusBar = "WordAI: 续写已停止";
            }
            else
            {
                // 开始续写
                _isContinueActive = true;
                _addin.Application.StatusBar = "WordAI: 正在续写...";
                _continueCts = new CancellationTokenSource();

                try
                {
                    await _addin.BackendClient.ContinueStreamAsync(
                        _continueCts.Token,
                        chunk => _addin.TextWriter.InsertText(chunk),
                        sessionId => _continueSessionId = sessionId
                    );
                }
                catch (OperationCanceledException) { }
                catch (Exception ex)
                {
                    _addin.Application.StatusBar = $"WordAI: 续写失败 - {ex.Message}";
                }
                finally
                {
                    _isContinueActive = false;
                }
            }
        }

        public bool IsContinueActive => _isContinueActive;

        public void Dispose()
        {
            Unregister();
            this.ReleaseHandle();
        }
    }
}
