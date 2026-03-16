using SharpShell.Attributes;
using SharpShell.Interop;
using SharpShell.SharpIconOverlayHandler;
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;

namespace ArtcoPsdOverlay
{
    /// <summary>
    /// Windows Explorer icon overlay handler for .psd files.
    ///
    /// Notes:
    /// - Explorer overlay slots are limited; registry key name ordering affects priority.
    /// - This handler only checks file extension; it does not parse PSD.
    /// </summary>
    [ComVisible(true)]
    [Guid("B9A7A4E3-6B1C-4D3B-AE6C-0B6C8C0E9F33")]
    [DisplayName("Artco PSD Overlay")]
    public class PsdOverlayHandler : SharpIconOverlayHandler
    {
        protected override bool CanShowOverlay(string path, FILE_ATTRIBUTE attributes)
        {
            if (string.IsNullOrWhiteSpace(path))
                return false;

            return path.EndsWith(".psd", StringComparison.OrdinalIgnoreCase);
        }

        protected override int GetPriority()
        {
            // 0 is the highest priority.
            // Actual overlay selection is also impacted by ShellIconOverlayIdentifiers key order.
            return 0;
        }

        private static Icon _cachedIcon;

        protected override Icon GetOverlayIcon()
        {
            // Explorer may call this frequently; cache the generated icon.
            if (_cachedIcon != null)
                return _cachedIcon;

            _cachedIcon = CreateBadgeIcon();
            return _cachedIcon;
        }

        private static Icon CreateBadgeIcon()
        {
            // Explorer scales overlay icons aggressively for large thumbnails.
            // If the text is too thin, it can disappear after scaling. Use path-based text.
            const int size = 32;
            const float pad = 5f;

            using (var bmp = new Bitmap(size, size, System.Drawing.Imaging.PixelFormat.Format32bppArgb))
            using (var g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.PixelOffsetMode = PixelOffsetMode.HighQuality;
                g.CompositingQuality = CompositingQuality.HighQuality;
                g.Clear(Color.Transparent);

                var badgeRect = new RectangleF(pad, pad, size - pad * 2, size - pad * 2);

                // Background: subtle dark rounded rect, no border.
                using (var path = CreateRoundedRect(badgeRect, 8f))
                using (var bg = new SolidBrush(Color.FromArgb(230, 22, 22, 26)))
                {
                    g.FillPath(bg, path);
                }

                DrawTextAsPath(g, "PSD", badgeRect);

                var hIcon = bmp.GetHicon();
                try
                {
                    return (Icon)Icon.FromHandle(hIcon).Clone();
                }
                finally
                {
                    DestroyIcon(hIcon);
                }
            }
        }

        private static void DrawTextAsPath(Graphics g, string text, RectangleF target)
        {
            using (var family = new FontFamily("Segoe UI"))
            using (var textPath = new GraphicsPath())
            {
                // Build text at origin with a larger em size, then scale to fit target.
                float emSize = 28f;
                var sf = new StringFormat(StringFormat.GenericDefault)
                {
                    Alignment = StringAlignment.Near,
                    LineAlignment = StringAlignment.Near
                };

                textPath.AddString(text, family, (int)FontStyle.Bold, emSize, new PointF(0, 0), sf);

                var bounds = textPath.GetBounds();
                if (bounds.Width <= 0.1f || bounds.Height <= 0.1f)
                    return;

                // Fit text into target with slight padding.
                float innerPad = 2.0f;
                var inner = RectangleF.Inflate(target, -innerPad, -innerPad);
                float scale = Math.Min(inner.Width / bounds.Width, inner.Height / bounds.Height);

                using (var m = new Matrix())
                {
                    // IMPORTANT: System.Drawing's Matrix methods default to MatrixOrder.Prepend,
                    // which can easily move the text out of bounds. Use Append explicitly.
                    m.Translate(-bounds.X, -bounds.Y, MatrixOrder.Append);
                    m.Scale(scale, scale, MatrixOrder.Append);

                    // Center into target.
                    var scaledW = bounds.Width * scale;
                    var scaledH = bounds.Height * scale;
                    float dx = inner.X + (inner.Width - scaledW) / 2f;
                    float dy = inner.Y + (inner.Height - scaledH) / 2f;
                    m.Translate(dx, dy, MatrixOrder.Append);

                    textPath.Transform(m);
                }


                // Optional subtle shadow to keep it legible when scaled.
                using (var shadow = (GraphicsPath)textPath.Clone())
                using (var shadowBrush = new SolidBrush(Color.FromArgb(120, 0, 0, 0)))
                {
                    using (var m2 = new Matrix())
                    {
                        m2.Translate(0.6f, 0.6f);
                        shadow.Transform(m2);
                    }
                    g.FillPath(shadowBrush, shadow);
                }

                using (var brush = new SolidBrush(Color.FromArgb(245, 255, 255, 255)))
                {
                    g.FillPath(brush, textPath);
                }
            }
        }



        private static GraphicsPath CreateRoundedRect(RectangleF rect, float radius)
        {
            var path = new GraphicsPath();
            var d = radius * 2f;

            path.AddArc(rect.X, rect.Y, d, d, 180, 90);
            path.AddArc(rect.Right - d, rect.Y, d, d, 270, 90);
            path.AddArc(rect.Right - d, rect.Bottom - d, d, d, 0, 90);
            path.AddArc(rect.X, rect.Bottom - d, d, d, 90, 90);
            path.CloseFigure();

            return path;
        }

        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool DestroyIcon(IntPtr hIcon);
    }
}

