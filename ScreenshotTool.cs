using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;

public static class ScreenshotTool
{
    private sealed class WatermarkConfig
    {
        public bool Enabled = true;
        public List<WatermarkField> Fields = new List<WatermarkField>();
        public List<string> Lines = new List<string>();
        public bool IncludeTimestamp = true;
        public string TimestampLabel = "";
        public string LabelSeparator = "";
        public string TimestampPrefix = "Time: ";
        public string TimestampFormat = "yyyy-MM-dd HH:mm:ss";
        public string FontFamily = "Microsoft YaHei";
        public float FontSize = 18;
        public string TextColor = "#FFFFFF";
        public string BackgroundColor = "#000000";
        public int BackgroundOpacity = 150;
        public int Padding = 10;
        public int MarginLeft = 16;
        public int MarginBottom = 16;
        public int LineSpacing = 4;
    }

    private sealed class WatermarkField
    {
        public string Label = "";
        public string Value = "";
    }

    [STAThread]
    public static int Main(string[] args)
    {
        try
        {
            string configPath = null;
            string outputDir = null;

            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--config" && i + 1 < args.Length)
                {
                    configPath = args[++i];
                }
                else if (args[i] == "--output-dir" && i + 1 < args.Length)
                {
                    outputDir = args[++i];
                }
            }

            if (string.IsNullOrWhiteSpace(configPath))
            {
                throw new ArgumentException("Missing --config <path>.");
            }

            Dictionary<string, object> config = ReadJsonObject(configPath);
            if (string.IsNullOrWhiteSpace(outputDir))
            {
                outputDir = GetString(config, "screenshot_dir", Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "screenshots"));
            }

            WatermarkConfig watermark = ReadWatermark(config);
            string file = Capture(outputDir, watermark);
            try
            {
                Console.OutputEncoding = Encoding.UTF8;
            }
            catch
            {
            }
            Console.WriteLine(file);
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.Message);
            return 1;
        }
    }

    private static Dictionary<string, object> ReadJsonObject(string path)
    {
        string json = File.ReadAllText(path, Encoding.UTF8);
        JavaScriptSerializer serializer = new JavaScriptSerializer();
        return serializer.Deserialize<Dictionary<string, object>>(json);
    }

    private static WatermarkConfig ReadWatermark(Dictionary<string, object> config)
    {
        WatermarkConfig result = new WatermarkConfig();
        if (!config.ContainsKey("watermark"))
        {
            return result;
        }

        Dictionary<string, object> watermark = config["watermark"] as Dictionary<string, object>;
        if (watermark == null)
        {
            return result;
        }

        result.Enabled = GetBool(watermark, "enabled", result.Enabled);
        result.IncludeTimestamp = GetBool(watermark, "include_timestamp", result.IncludeTimestamp);
        result.TimestampLabel = GetString(watermark, "timestamp_label", result.TimestampLabel);
        result.LabelSeparator = GetString(watermark, "label_separator", result.LabelSeparator);
        result.TimestampPrefix = GetString(watermark, "timestamp_prefix", result.TimestampPrefix);
        result.TimestampFormat = GetString(watermark, "timestamp_format", result.TimestampFormat);
        result.FontFamily = GetString(watermark, "font_family", result.FontFamily);
        result.FontSize = GetFloat(watermark, "font_size", result.FontSize);
        result.TextColor = GetString(watermark, "text_color", result.TextColor);
        result.BackgroundColor = GetString(watermark, "background_color", result.BackgroundColor);
        result.BackgroundOpacity = Math.Max(0, Math.Min(255, GetInt(watermark, "background_opacity", result.BackgroundOpacity)));
        result.Padding = GetInt(watermark, "padding", result.Padding);
        result.MarginLeft = GetInt(watermark, "margin_left", result.MarginLeft);
        result.MarginBottom = GetInt(watermark, "margin_bottom", result.MarginBottom);
        result.LineSpacing = GetInt(watermark, "line_spacing", result.LineSpacing);

        object[] fields = null;
        if (watermark.ContainsKey("fields"))
        {
            fields = watermark["fields"] as object[];
        }
        if (fields != null)
        {
            foreach (object field in fields)
            {
                Dictionary<string, object> item = field as Dictionary<string, object>;
                if (item == null)
                {
                    continue;
                }

                result.Fields.Add(new WatermarkField
                {
                    Label = GetString(item, "label", ""),
                    Value = GetString(item, "value", "")
                });
            }
        }

        object[] lines = null;
        if (watermark.ContainsKey("lines"))
        {
            lines = watermark["lines"] as object[];
        }
        if (lines != null)
        {
            foreach (object line in lines)
            {
                if (line != null)
                {
                    result.Lines.Add(Convert.ToString(line));
                }
            }
        }

        return result;
    }

    private static string Capture(string outputDir, WatermarkConfig watermark)
    {
        Directory.CreateDirectory(outputDir);
        Rectangle bounds = Rectangle.Empty;
        foreach (Screen screen in Screen.AllScreens)
        {
            bounds = Rectangle.Union(bounds, screen.Bounds);
        }

        using (Bitmap bitmap = new Bitmap(bounds.Width, bounds.Height))
        using (Graphics graphics = Graphics.FromImage(bitmap))
        {
            graphics.CopyFromScreen(bounds.Location, Point.Empty, bounds.Size);
            graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.HighQuality;
            graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;
            DrawWatermark(graphics, new Rectangle(0, 0, bounds.Width, bounds.Height), watermark);

            string file = Path.Combine(outputDir, "screenshot-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".png");
            bitmap.Save(file, ImageFormat.Png);
            return file;
        }
    }

    private static void DrawWatermark(Graphics graphics, Rectangle imageBounds, WatermarkConfig watermark)
    {
        if (!watermark.Enabled)
        {
            return;
        }

        List<string> lines = new List<string>();
        string separator = watermark.LabelSeparator;
        if (string.IsNullOrEmpty(separator))
        {
            separator = watermark.Fields.Count > 0 || !string.IsNullOrWhiteSpace(watermark.TimestampLabel) ? ": " : "";
        }

        foreach (WatermarkField field in watermark.Fields)
        {
            if (string.IsNullOrWhiteSpace(field.Label) && string.IsNullOrWhiteSpace(field.Value))
            {
                continue;
            }
            if (string.IsNullOrWhiteSpace(field.Label))
            {
                lines.Add(field.Value);
            }
            else
            {
                lines.Add(field.Label + separator + field.Value);
            }
        }

        lines.AddRange(watermark.Lines);
        if (watermark.IncludeTimestamp)
        {
            string timestamp = DateTime.Now.ToString(watermark.TimestampFormat);
            if (!string.IsNullOrWhiteSpace(watermark.TimestampLabel))
            {
                lines.Add(watermark.TimestampLabel + separator + timestamp);
            }
            else
            {
                lines.Add(watermark.TimestampPrefix + timestamp);
            }
        }
        if (lines.Count == 0)
        {
            return;
        }

        using (Font font = new Font(watermark.FontFamily, watermark.FontSize, FontStyle.Regular, GraphicsUnit.Pixel))
        using (StringFormat format = new StringFormat(StringFormatFlags.NoClip))
        using (Brush backgroundBrush = new SolidBrush(ParseColor(watermark.BackgroundColor, watermark.BackgroundOpacity)))
        using (Brush textBrush = new SolidBrush(ParseColor(watermark.TextColor, 255)))
        {
            float maxWidth = 0;
            List<float> heights = new List<float>();
            foreach (string line in lines)
            {
                SizeF size = graphics.MeasureString(line, font);
                maxWidth = Math.Max(maxWidth, size.Width);
                heights.Add(size.Height);
            }

            float textHeight = 0;
            foreach (float height in heights)
            {
                textHeight += height;
            }
            if (lines.Count > 1)
            {
                textHeight += (lines.Count - 1) * watermark.LineSpacing;
            }

            int boxWidth = (int)Math.Ceiling(maxWidth + watermark.Padding * 2);
            int boxHeight = (int)Math.Ceiling(textHeight + watermark.Padding * 2);
            int boxX = imageBounds.Left + watermark.MarginLeft;
            int boxY = imageBounds.Bottom - watermark.MarginBottom - boxHeight;
            if (boxY < imageBounds.Top)
            {
                boxY = imageBounds.Top + watermark.MarginBottom;
            }

            if (watermark.BackgroundOpacity > 0)
            {
                graphics.FillRectangle(backgroundBrush, new Rectangle(boxX, boxY, boxWidth, boxHeight));
            }

            float cursorY = boxY + watermark.Padding;
            for (int i = 0; i < lines.Count; i++)
            {
                graphics.DrawString(lines[i], font, textBrush, new PointF(boxX + watermark.Padding, cursorY), format);
                cursorY += heights[i] + watermark.LineSpacing;
            }
        }
    }

    private static Color ParseColor(string hex, int alpha)
    {
        string value = string.IsNullOrWhiteSpace(hex) ? "FFFFFF" : hex.Trim();
        if (value.StartsWith("#"))
        {
            value = value.Substring(1);
        }
        if (value.Length != 6)
        {
            throw new ArgumentException("Color must use #RRGGBB format: " + hex);
        }

        int r = Convert.ToInt32(value.Substring(0, 2), 16);
        int g = Convert.ToInt32(value.Substring(2, 2), 16);
        int b = Convert.ToInt32(value.Substring(4, 2), 16);
        return Color.FromArgb(alpha, r, g, b);
    }

    private static string GetString(Dictionary<string, object> data, string key, string defaultValue)
    {
        return data.ContainsKey(key) && data[key] != null ? Convert.ToString(data[key]) : defaultValue;
    }

    private static bool GetBool(Dictionary<string, object> data, string key, bool defaultValue)
    {
        return data.ContainsKey(key) && data[key] != null ? Convert.ToBoolean(data[key]) : defaultValue;
    }

    private static int GetInt(Dictionary<string, object> data, string key, int defaultValue)
    {
        return data.ContainsKey(key) && data[key] != null ? Convert.ToInt32(data[key]) : defaultValue;
    }

    private static float GetFloat(Dictionary<string, object> data, string key, float defaultValue)
    {
        return data.ContainsKey(key) && data[key] != null ? Convert.ToSingle(data[key]) : defaultValue;
    }
}
