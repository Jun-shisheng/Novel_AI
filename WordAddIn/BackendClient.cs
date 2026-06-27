using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace WordAI
{
    public class BackendClient
    {
        private readonly HttpClient _http;
        private readonly string _baseUrl;
        private Dictionary<string, object> _cachedSummary;
        private List<string> _cachedStyleTags;

        public BackendClient(string baseUrl)
        {
            _baseUrl = baseUrl.TrimEnd('/');
            _http = new HttpClient { Timeout = TimeSpan.FromMinutes(5) };
        }

        /// <summary>润色文本。</summary>
        public async Task<string> PolishAsync(string text)
        {
            var req = new
            {
                text,
                context_before = ContextBefore(500),
                context_after = ContextAfter(200),
                summary = GetCachedSummary(),
                style_tags = GetCachedStyleTags(),
            };
            var json = JsonConvert.SerializeObject(req);
            var content = new StringContent(json, Encoding.UTF8, "application/json");
            var resp = await _http.PostAsync($"{_baseUrl}/api/polish", content);
            resp.EnsureSuccessStatusCode();
            var result = JObject.Parse(await resp.Content.ReadAsStringAsync());
            return result["polished_text"]?.Value<string>() ?? "";
        }

        /// <summary>流式续写，每收到 chunk 回调 onChunk。</summary>
        public async Task ContinueStreamAsync(
            CancellationToken ct,
            Action<string> onChunk,
            Action<string> onSessionId)
        {
            var req = new
            {
                context_before = ContextBefore(3000),
                context_after = ContextAfter(500),
                summary = GetCachedSummary(),
                style_tags = GetCachedStyleTags(),
            };
            var json = JsonConvert.SerializeObject(req);
            var request = new HttpRequestMessage(HttpMethod.Post, $"{_baseUrl}/api/continue")
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json"),
            };
            request.Headers.Accept.Add(new System.Net.Http.Headers.MediaTypeWithQualityHeaderValue("text/event-stream"));

            var resp = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
            resp.EnsureSuccessStatusCode();

            using var stream = await resp.Content.ReadAsStreamAsync();
            using var reader = new StreamReader(stream);

            string currentEvent = "";
            while (!reader.EndOfStream && !ct.IsCancellationRequested)
            {
                string line = await reader.ReadLineAsync();
                if (line == null) break;
                if (line.StartsWith("event: "))
                {
                    currentEvent = line.Substring(7).Trim();
                }
                else if (line.StartsWith("data: "))
                {
                    string data = line.Substring(6);
                    if (currentEvent == "session")
                    {
                        onSessionId?.Invoke(data);
                    }
                    else if (currentEvent == "chunk")
                    {
                        onChunk?.Invoke(data);
                    }
                    else if (currentEvent == "done" || currentEvent == "cancelled")
                    {
                        break;
                    }
                }
            }
        }

        /// <summary>停止续写，返回最后一个完整句。</summary>
        public async Task<string> StopAsync(string sessionId)
        {
            var resp = await _http.PostAsync($"{_baseUrl}/api/stop?session_id={sessionId}", null);
            resp.EnsureSuccessStatusCode();
            return "";
        }

        /// <summary>生成概要。</summary>
        public async Task<Dictionary<string, object>> GenerateSummaryAsync(string fullText, string docPath)
        {
            var req = new { text = fullText, doc_path = docPath };
            var content = new StringContent(JsonConvert.SerializeObject(req), Encoding.UTF8, "application/json");
            var resp = await _http.PostAsync($"{_baseUrl}/api/summary/generate", content);
            resp.EnsureSuccessStatusCode();
            var result = JObject.Parse(await resp.Content.ReadAsStringAsync());
            var summary = result["summary"]?.ToObject<Dictionary<string, object>>() ?? new Dictionary<string, object>();
            _cachedSummary = summary;

            if (summary.TryGetValue("风格标签", out var tags) && tags is JArray arr)
            {
                _cachedStyleTags = arr.ToObject<List<string>>();
            }
            return summary;
        }

        /// <summary>增量更新概要。</summary>
        public async Task UpdateSummaryAsync(string newText, string docPath)
        {
            var req = new { new_text = newText, doc_path = docPath };
            var content = new StringContent(JsonConvert.SerializeObject(req), Encoding.UTF8, "application/json");
            var resp = await _http.PostAsync($"{_baseUrl}/api/summary/update", content);
            resp.EnsureSuccessStatusCode();
            _cachedSummary = null;
        }

        /// <summary>加载已有概要到缓存。</summary>
        public async Task LoadSummaryAsync(string docPath = "")
        {
            var resp = await _http.GetAsync($"{_baseUrl}/api/summary/get?doc_path={Uri.EscapeDataString(docPath)}");
            if (resp.IsSuccessStatusCode)
            {
                var result = JObject.Parse(await resp.Content.ReadAsStringAsync());
                var summary = result["summary"]?.ToObject<Dictionary<string, object>>();
                if (summary != null && summary.Count > 0)
                {
                    _cachedSummary = summary;
                    if (summary.TryGetValue("风格标签", out var tags) && tags is JArray arr)
                    {
                        _cachedStyleTags = arr.ToObject<List<string>>();
                    }
                }
            }
        }

        public Dictionary<string, object> GetCachedSummary() => _cachedSummary ?? new Dictionary<string, object>();
        public List<string> GetCachedStyleTags() => _cachedStyleTags ?? new List<string>();

        public Func<int, string> ContextBefore { get; set; } = (_) => "";
        public Func<int, string> ContextAfter { get; set; } = (_) => "";

        public async Task<Dictionary<string, object>> GetSettingsAsync()
        {
            var resp = await _http.GetAsync($"{_baseUrl}/api/settings");
            resp.EnsureSuccessStatusCode();
            var result = JObject.Parse(await resp.Content.ReadAsStringAsync());
            return result["config"]?.ToObject<Dictionary<string, object>>() ?? new Dictionary<string, object>();
        }

        public async Task SaveSettingsAsync(Dictionary<string, object> config)
        {
            var req = new { config };
            var content = new StringContent(JsonConvert.SerializeObject(req), Encoding.UTF8, "application/json");
            var resp = await _http.PostAsync($"{_baseUrl}/api/settings", content);
            resp.EnsureSuccessStatusCode();
        }
    }
}
