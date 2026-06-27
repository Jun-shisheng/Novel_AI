using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
using Microsoft.Office.Tools;
using Word = Microsoft.Office.Interop.Word;

namespace WordAI
{
    public partial class ThisAddIn
    {
        private Process _pythonProcess;
        private HotkeyManager _hotkeyManager;
        private ContextExtractor _contextExtractor;
        private TextWriter _textWriter;
        private BackendClient _backendClient;

        public HotkeyManager HotkeyManager => _hotkeyManager;
        public ContextExtractor ContextExtractor => _contextExtractor;
        public TextWriter TextWriter => _textWriter;
        public BackendClient BackendClient => _backendClient;

        private void ThisAddIn_Startup(object sender, EventArgs e)
        {
            StartPythonBackend();
            _backendClient = new BackendClient("http://127.0.0.1:19800");
            _contextExtractor = new ContextExtractor(this.Application);
            _textWriter = new TextWriter(this.Application);
            // 注入上下文提取钩子
            _backendClient.ContextBefore = _contextExtractor.GetTextBefore;
            _backendClient.ContextAfter = _contextExtractor.GetTextAfter;
            // 加载已有概要
            string docPath = _contextExtractor.GetDocPath();
            if (!string.IsNullOrEmpty(docPath))
            {
                _ = _backendClient.LoadSummaryAsync(docPath);
            }
            _hotkeyManager = new HotkeyManager(this);
            _hotkeyManager.Register();
        }

        private void ThisAddIn_Shutdown(object sender, EventArgs e)
        {
            _hotkeyManager?.Unregister();
            StopPythonBackend();
        }

        private void StartPythonBackend()
        {
            string backendDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                "WordAI", "backend");
            // 实际部署时指向 G:\WordAI\backend
            backendDir = @"G:\WordAI\backend";

            var psi = new ProcessStartInfo
            {
                FileName = Path.Combine(backendDir, "venv", "Scripts", "python.exe"),
                Arguments = Path.Combine(backendDir, "main.py"),
                WorkingDirectory = backendDir,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };

            _pythonProcess = new Process { StartInfo = psi, EnableRaisingEvents = true };
            _pythonProcess.Start();
        }

        private void StopPythonBackend()
        {
            if (_pythonProcess != null && !_pythonProcess.HasExited)
            {
                _pythonProcess.Kill();
                _pythonProcess.WaitForExit(3000);
                _pythonProcess.Dispose();
            }
        }
    }
}
