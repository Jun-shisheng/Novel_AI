using System;
using System.Collections.Generic;
using System.Windows.Forms;

namespace WordAI
{
    public partial class SettingsForm : Form
    {
        private readonly ThisAddIn _addin;
        private TextBox txtApiKey;
        private NumericUpDown numBefore;
        private NumericUpDown numAfter;
        private NumericUpDown numPolishBefore;
        private NumericUpDown numPolishAfter;
        private NumericUpDown numExpandRatio;
        private TextBox txtSettingFile;
        private ComboBox cmbModel;
        private Button btnSave;
        private Button btnCancel;

        public SettingsForm(ThisAddIn addin)
        {
            _addin = addin;
            InitializeComponent();
            LoadSettings();
        }

        private void InitializeComponent()
        {
            this.Text = "WordAI 设置";
            this.Size = new System.Drawing.Size(480, 420);
            this.FormBorderStyle = FormBorderStyle.FixedDialog;
            this.MaximizeBox = false;
            this.MinimizeBox = false;
            this.StartPosition = FormStartPosition.CenterParent;

            int y = 16;
            int labelX = 16;
            int inputX = 140;
            int inputW = 300;

            // API Key
            var lblApiKey = new Label { Text = "DeepSeek API Key:", Left = labelX, Top = y, Width = 120 };
            txtApiKey = new TextBox { Left = inputX, Top = y, Width = inputW, PasswordChar = '*' };
            this.Controls.Add(lblApiKey);
            this.Controls.Add(txtApiKey);
            y += 32;

            // Model
            var lblModel = new Label { Text = "模型:", Left = labelX, Top = y, Width = 120 };
            cmbModel = new ComboBox { Left = inputX, Top = y, Width = inputW };
            cmbModel.Items.AddRange(new[] { "deepseek-chat", "deepseek-reasoner" });
            this.Controls.Add(lblModel);
            this.Controls.Add(cmbModel);
            y += 32;

            // 续写字数
            var lblBefore = new Label { Text = "续写前文长度:", Left = labelX, Top = y, Width = 120 };
            numBefore = new NumericUpDown { Left = inputX, Top = y, Width = 100, Minimum = 500, Maximum = 10000, Increment = 500 };
            this.Controls.Add(lblBefore);
            this.Controls.Add(numBefore);
            y += 32;

            var lblAfter = new Label { Text = "续写后文长度:", Left = labelX, Top = y, Width = 120 };
            numAfter = new NumericUpDown { Left = inputX, Top = y, Width = 100, Minimum = 0, Maximum = 5000, Increment = 100 };
            this.Controls.Add(lblAfter);
            this.Controls.Add(numAfter);
            y += 32;

            // 润色参数
            var lblPolishBefore = new Label { Text = "润色前文长度:", Left = labelX, Top = y, Width = 120 };
            numPolishBefore = new NumericUpDown { Left = inputX, Top = y, Width = 100, Minimum = 100, Maximum = 5000, Increment = 100 };
            this.Controls.Add(lblPolishBefore);
            this.Controls.Add(numPolishBefore);
            y += 32;

            var lblPolishAfter = new Label { Text = "润色后文长度:", Left = labelX, Top = y, Width = 120 };
            numPolishAfter = new NumericUpDown { Left = inputX, Top = y, Width = 100, Minimum = 0, Maximum = 3000, Increment = 100 };
            this.Controls.Add(lblPolishAfter);
            this.Controls.Add(numPolishAfter);
            y += 32;

            var lblExpand = new Label { Text = "润色扩写比例:", Left = labelX, Top = y, Width = 120 };
            numExpandRatio = new NumericUpDown { Left = inputX, Top = y, Width = 100, Minimum = 1.0M, Maximum = 3.0M, Increment = 0.1M, DecimalPlaces = 1, Value = 1.3M };
            this.Controls.Add(lblExpand);
            this.Controls.Add(numExpandRatio);
            y += 32;

            // 设定文件
            var lblSetting = new Label { Text = "设定文件路径:", Left = labelX, Top = y, Width = 120 };
            txtSettingFile = new TextBox { Left = inputX, Top = y, Width = inputW - 40 };
            var btnBrowse = new Button { Text = "...", Left = inputX + inputW - 34, Top = y - 1, Width = 34 };
            btnBrowse.Click += (s, e) =>
            {
                var dlg = new OpenFileDialog { Filter = "Word 文档|*.docx", Title = "选择设定文件" };
                if (dlg.ShowDialog() == DialogResult.OK)
                    txtSettingFile.Text = dlg.FileName;
            };
            this.Controls.Add(lblSetting);
            this.Controls.Add(txtSettingFile);
            this.Controls.Add(btnBrowse);
            y += 42;

            // 按钮
            btnSave = new Button { Text = "保存", Left = inputX, Top = y, Width = 80 };
            btnSave.Click += BtnSave_Click;
            btnCancel = new Button { Text = "取消", Left = inputX + 100, Top = y, Width = 80 };
            btnCancel.Click += (s, e) => this.Close();
            this.Controls.Add(btnSave);
            this.Controls.Add(btnCancel);
        }

        private async void LoadSettings()
        {
            try
            {
                var cfg = await _addin.BackendClient.GetSettingsAsync();
                if (cfg.TryGetValue("api_key", out var key)) txtApiKey.Text = key?.ToString() ?? "";
                if (cfg.TryGetValue("model", out var model)) cmbModel.Text = model?.ToString() ?? "deepseek-chat";
                if (cfg.TryGetValue("continue_before_chars", out var cb)) numBefore.Value = Convert.ToInt32(cb);
                if (cfg.TryGetValue("continue_after_chars", out var ca)) numAfter.Value = Convert.ToInt32(ca);
                if (cfg.TryGetValue("polish_before_chars", out var pb)) numPolishBefore.Value = Convert.ToInt32(pb);
                if (cfg.TryGetValue("polish_after_chars", out var pa)) numPolishAfter.Value = Convert.ToInt32(pa);
                if (cfg.TryGetValue("polish_expand_ratio", out var er)) numExpandRatio.Value = Convert.ToDecimal(er);
                if (cfg.TryGetValue("setting_file_path", out var sf)) txtSettingFile.Text = sf?.ToString() ?? "";
            }
            catch { /* 首次使用，后端未启动 */ }
        }

        private async void BtnSave_Click(object sender, EventArgs e)
        {
            var cfg = new Dictionary<string, object>
            {
                ["api_key"] = txtApiKey.Text,
                ["model"] = cmbModel.Text,
                ["continue_before_chars"] = (int)numBefore.Value,
                ["continue_after_chars"] = (int)numAfter.Value,
                ["polish_before_chars"] = (int)numPolishBefore.Value,
                ["polish_after_chars"] = (int)numPolishAfter.Value,
                ["polish_expand_ratio"] = (double)numExpandRatio.Value,
                ["setting_file_path"] = txtSettingFile.Text,
            };
            await _addin.BackendClient.SaveSettingsAsync(cfg);
            this.Close();
            _addin.Application.StatusBar = "WordAI: 设置已保存";
        }
    }
}
