using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using SharpShell.Attributes;
using SharpShell.SharpThumbnailHandler;

namespace ArtcoShellExtension
{
    /// <summary>
    /// Artco 图片格式缩略图处理器
    /// 在图片缩略图右下角显示文件格式标签（如 PSD、PNG、JPG 等）
    /// </summary>
    [ComVisible(true)]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".psd")]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".psb")]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".png")]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".jpg")]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".jpeg")]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".gif")]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".bmp")]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".webp")]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".tiff")]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".tif")]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".ico")]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".svg")]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".raw")]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".cr2")]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".nef")]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".arw")]
    [COMServerAssociation(AssociationType.ClassOfExtension, ".dng")]
    [Guid("B2C3D4E5-F6A7-8901-BCDE-F12345678901")]
    public class ImageFormatThumbnailHandler : SharpThumbnailHandler
    {
        // 格式对应的颜色配置
        private static readonly Dictionary<string, Color> FormatColors = new Dictionary<string, Color>(StringComparer.OrdinalIgnoreCase)
        {
            // Adobe 格式 - 蓝色系
            { "PSD", Color.FromArgb(0, 102, 204) },
            { "PSB", Color.FromArgb(0, 82, 164) },
            
            // 常见图片格式 - 绿色系
            { "PNG", Color.FromArgb(46, 139, 87) },
            { "JPG", Color.FromArgb(34, 139, 34) },
            { "JPEG", Color.FromArgb(34, 139, 34) },
            { "GIF", Color.FromArgb(0, 128, 128) },
            { "BMP", Color.FromArgb(70, 130, 80) },
            { "WEBP", Color.FromArgb(60, 150, 60) },
            
            // TIFF 格式 - 紫色系
            { "TIFF", Color.FromArgb(128, 0, 128) },
            { "TIF", Color.FromArgb(128, 0, 128) },
            
            // RAW 格式 - 橙色系
            { "RAW", Color.FromArgb(255, 140, 0) },
            { "CR2", Color.FromArgb(230, 120, 0) },
            { "NEF", Color.FromArgb(255, 165, 0) },
            { "ARW", Color.FromArgb(255, 150, 50) },
            { "DNG", Color.FromArgb(210, 105, 30) },
            
            // 其他格式
            { "ICO", Color.FromArgb(100, 100, 100) },
            { "SVG", Color.FromArgb(255, 165, 0) },
        };

        /// <summary>
        /// 获取带格式标签的缩略图
        /// </summary>
        protected override Bitmap GetThumbnailImage(uint width)
        {
            try
            {
                // 获取文件路径和扩展名
                string filePath = SelectedItemPath;
                string extension = Path.GetExtension(filePath)?.ToUpperInvariant()?.TrimStart('.') ?? "";

                // 加载原始缩略图
                Bitmap thumbnail = LoadOriginalThumbnail(filePath, (int)width);
                
                if (thumbnail == null)
                {
                    return null;
                }

                // 在缩略图上绘制格式标签
                DrawFormatLabel(thumbnail, extension);

                return thumbnail;
            }
            catch (Exception)
            {
                return null;
            }
        }

        /// <summary>
        /// 加载原始缩略图
        /// </summary>
        private Bitmap LoadOriginalThumbnail(string filePath, int targetSize)
        {
            try
            {
                string ext = Path.GetExtension(filePath)?.ToLowerInvariant();

                // PSD/PSB 文件特殊处理
                if (ext == ".psd" || ext == ".psb")
                {
                    return LoadPsdThumbnail(filePath, targetSize);
                }

                // 其他图片格式使用 GDI+ 加载
                using (var image = Image.FromFile(filePath))
                {
                    return ResizeImage(image, targetSize);
                }
            }
            catch
            {
                // 如果加载失败，创建一个带问号的默认缩略图
                return CreateDefaultThumbnail(targetSize);
            }
        }

        /// <summary>
        /// 加载 PSD 文件的缩略图
        /// </summary>
        private Bitmap LoadPsdThumbnail(string filePath, int targetSize)
        {
            try
            {
                // 尝试读取 PSD 文件的嵌入缩略图
                using (var fs = new FileStream(filePath, FileMode.Open, FileAccess.Read, FileShare.Read))
                using (var reader = new BinaryReader(fs))
                {
                    // 检查 PSD 签名 "8BPS"
                    byte[] signature = reader.ReadBytes(4);
                    if (signature[0] != 0x38 || signature[1] != 0x42 || 
                        signature[2] != 0x50 || signature[3] != 0x53)
                    {
                        return CreateDefaultThumbnail(targetSize);
                    }

                    // 跳过版本号
                    reader.ReadInt16();
                    
                    // 跳过保留字节 (6 bytes)
                    reader.ReadBytes(6);
                    
                    // 读取通道数
                    short channels = ReadBigEndianInt16(reader);
                    
                    // 读取图像尺寸
                    int height = ReadBigEndianInt32(reader);
                    int width = ReadBigEndianInt32(reader);

                    // 创建带尺寸信息的缩略图
                    var thumb = CreateDefaultThumbnail(targetSize);
                    using (var g = Graphics.FromImage(thumb))
                    {
                        string sizeText = $"{width}x{height}";
                        using (var font = new Font("Segoe UI", 8f, FontStyle.Regular))
                        {
                            var textSize = g.MeasureString(sizeText, font);
                            float x = (thumb.Width - textSize.Width) / 2;
                            float y = thumb.Height / 2 + 5;
                            g.DrawString(sizeText, font, Brushes.Gray, x, y);
                        }
                    }
                    return thumb;
                }
            }
            catch
            {
                return CreateDefaultThumbnail(targetSize);
            }
        }

        /// <summary>
        /// 大端序读取 Int16
        /// </summary>
        private short ReadBigEndianInt16(BinaryReader reader)
        {
            byte[] bytes = reader.ReadBytes(2);
            Array.Reverse(bytes);
            return BitConverter.ToInt16(bytes, 0);
        }

        /// <summary>
        /// 大端序读取 Int32
        /// </summary>
        private int ReadBigEndianInt32(BinaryReader reader)
        {
            byte[] bytes = reader.ReadBytes(4);
            Array.Reverse(bytes);
            return BitConverter.ToInt32(bytes, 0);
        }

        /// <summary>
        /// 创建默认缩略图
        /// </summary>
        private Bitmap CreateDefaultThumbnail(int size)
        {
            var bmp = new Bitmap(size, size, PixelFormat.Format32bppArgb);
            using (var g = Graphics.FromImage(bmp))
            {
                g.Clear(Color.FromArgb(40, 40, 40));
                
                // 绘制一个简单的图片图标
                int iconSize = size / 3;
                int x = (size - iconSize) / 2;
                int y = (size - iconSize) / 2 - 10;
                
                using (var pen = new Pen(Color.Gray, 2))
                {
                    g.DrawRectangle(pen, x, y, iconSize, iconSize);
                    // 绘制山形
                    var points = new Point[]
                    {
                        new Point(x + 5, y + iconSize - 5),
                        new Point(x + iconSize / 3, y + iconSize / 2),
                        new Point(x + iconSize / 2, y + iconSize - 10),
                        new Point(x + iconSize - 10, y + iconSize / 3),
                        new Point(x + iconSize - 5, y + iconSize - 5)
                    };
                    g.DrawLines(pen, points);
                }
            }
            return bmp;
        }

        /// <summary>
        /// 调整图像大小
        /// </summary>
        private Bitmap ResizeImage(Image image, int targetSize)
        {
            // 计算缩放比例，保持纵横比
            float scale = Math.Min((float)targetSize / image.Width, (float)targetSize / image.Height);
            int newWidth = (int)(image.Width * scale);
            int newHeight = (int)(image.Height * scale);

            var bmp = new Bitmap(targetSize, targetSize, PixelFormat.Format32bppArgb);
            using (var g = Graphics.FromImage(bmp))
            {
                g.Clear(Color.Transparent);
                g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                g.SmoothingMode = SmoothingMode.HighQuality;
                g.PixelOffsetMode = PixelOffsetMode.HighQuality;

                // 居中绘制
                int x = (targetSize - newWidth) / 2;
                int y = (targetSize - newHeight) / 2;
                g.DrawImage(image, x, y, newWidth, newHeight);
            }
            return bmp;
        }

        /// <summary>
        /// 在缩略图右下角绘制格式标签
        /// </summary>
        private void DrawFormatLabel(Bitmap thumbnail, string format)
        {
            if (string.IsNullOrEmpty(format))
                return;

            // 标准化格式名称
            string displayFormat = format.ToUpperInvariant();
            if (displayFormat == "JPEG") displayFormat = "JPG";
            if (displayFormat == "TIFF") displayFormat = "TIF";

            using (var g = Graphics.FromImage(thumbnail))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;

                // 根据缩略图大小调整字体
                float fontSize = Math.Max(8f, thumbnail.Width / 12f);
                using (var font = new Font("Segoe UI", fontSize, FontStyle.Bold))
                {
                    var textSize = g.MeasureString(displayFormat, font);
                    
                    // 计算标签位置（右下角）
                    int padding = 3;
                    int margin = 4;
                    int labelWidth = (int)textSize.Width + padding * 2;
                    int labelHeight = (int)textSize.Height + padding;
                    int x = thumbnail.Width - labelWidth - margin;
                    int y = thumbnail.Height - labelHeight - margin;

                    // 获取格式对应的颜色
                    Color bgColor = GetFormatColor(format);

                    // 绘制圆角矩形背景
                    var labelRect = new Rectangle(x, y, labelWidth, labelHeight);
                    using (var bgBrush = new SolidBrush(bgColor))
                    {
                        DrawRoundedRectangle(g, labelRect, 3, bgBrush);
                    }

                    // 绘制文字
                    using (var textBrush = new SolidBrush(Color.White))
                    {
                        g.DrawString(displayFormat, font, textBrush, 
                            x + padding, y + padding / 2);
                    }
                }
            }
        }

        /// <summary>
        /// 获取格式对应的背景颜色
        /// </summary>
        private Color GetFormatColor(string format)
        {
            if (FormatColors.TryGetValue(format.ToUpperInvariant(), out Color color))
            {
                return color;
            }
            return Color.FromArgb(80, 80, 80); // 默认灰色
        }

        /// <summary>
        /// 绘制圆角矩形
        /// </summary>
        private void DrawRoundedRectangle(Graphics g, Rectangle rect, int radius, Brush brush)
        {
            using (var path = new GraphicsPath())
            {
                int diameter = radius * 2;
                var arc = new Rectangle(rect.X, rect.Y, diameter, diameter);

                // 左上角
                path.AddArc(arc, 180, 90);
                
                // 右上角
                arc.X = rect.Right - diameter;
                path.AddArc(arc, 270, 90);
                
                // 右下角
                arc.Y = rect.Bottom - diameter;
                path.AddArc(arc, 0, 90);
                
                // 左下角
                arc.X = rect.Left;
                path.AddArc(arc, 90, 90);

                path.CloseFigure();
                g.FillPath(brush, path);
            }
        }
    }
}
