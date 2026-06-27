using System;
using System.Windows.Forms;
using Microsoft.Office.Core;
using Microsoft.Office.Tools.Ribbon;

namespace WordAI
{
    public class Ribbon : OfficeRibbon
    {
        private ThisAddIn _addin;

        public void Ribbon_Load(Office.IRibbonUI ribbonUI)
        {
            this.RibbonUI = ribbonUI;
            _addin = Globals.ThisAddIn;
        }

        public async void OnPolishClick(Office.IRibbonControl control)
        {
            try
            {
                string text = _addin.ContextExtractor.GetSelectedText();
                if (string.IsNullOrWhiteSpace(text))
                {
                    _addin.Application.StatusBar = "WordAI: 请先选中文本";
                    return;
                }
                _addin.Application.StatusBar = "WordAI: 正在润色...";
                _addin.BackendClient.ContextBefore = _addin.ContextExtractor.GetTextBefore;
                _addin.BackendClient.ContextAfter = _addin.ContextExtractor.GetTextAfter;
                string polished = await _addin.BackendClient.PolishAsync(text);
                _addin.TextWriter.ReplaceSelection(polished);
                _addin.Application.StatusBar = "WordAI: 润色完成";
            }
            catch (Exception ex)
            {
                _addin.Application.StatusBar = $"WordAI: 失败 - {ex.Message}";
            }
        }

        public void OnContinueToggle(Office.IRibbonControl control)
        {
            _addin.Application.StatusBar = "WordAI: 请使用 Ctrl+Enter 切换续写";
        }

        public async void OnGenerateSummary(Office.IRibbonControl control)
        {
            try
            {
                string fullText = _addin.ContextExtractor.GetSelectedText();
                if (string.IsNullOrWhiteSpace(fullText))
                {
                    fullText = _addin.ContextExtractor.GetFullText();
                }
                if (string.IsNullOrWhiteSpace(fullText))
                {
                    _addin.Application.StatusBar = "WordAI: 无可用文本";
                    return;
                }
                _addin.Application.StatusBar = "WordAI: 正在生成概要...";
                string docPath = _addin.ContextExtractor.GetDocPath();
                await _addin.BackendClient.GenerateSummaryAsync(fullText, docPath);
                _addin.Application.StatusBar = "WordAI: 概要生成完成";

                var summary = _addin.BackendClient.GetCachedSummary();
                MessageBox.Show(
                    Newtonsoft.Json.JsonConvert.SerializeObject(summary, Newtonsoft.Json.Formatting.Indented),
                    "作品概要",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
            }
            catch (Exception ex)
            {
                _addin.Application.StatusBar = $"WordAI: 概要生成失败 - {ex.Message}";
            }
        }

        public async void OnUpdateSummary(Office.IRibbonControl control)
        {
            try
            {
                string newText = _addin.ContextExtractor.GetSelectedText();
                if (string.IsNullOrWhiteSpace(newText))
                {
                    _addin.Application.StatusBar = "WordAI: 请选中新增文本";
                    return;
                }
                _addin.Application.StatusBar = "WordAI: 正在更新概要...";
                string docPath = _addin.ContextExtractor.GetDocPath();
                await _addin.BackendClient.UpdateSummaryAsync(newText, docPath);
                _addin.Application.StatusBar = "WordAI: 概要更新完成";
            }
            catch (Exception ex)
            {
                _addin.Application.StatusBar = $"WordAI: 更新失败 - {ex.Message}";
            }
        }

        public void OnSettings(Office.IRibbonControl control)
        {
            var form = new SettingsForm(_addin);
            form.ShowDialog();
        }
    }
}
