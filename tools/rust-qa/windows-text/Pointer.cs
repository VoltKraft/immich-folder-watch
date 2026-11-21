namespace IfwQaText {
    using System;
    using System.ComponentModel;
    using System.Runtime.InteropServices;

    public static class Input {
        [StructLayout(LayoutKind.Sequential)] struct Pointer {
            public int x, y;
            public uint data, flags, time;
            public UIntPtr extra;
        }
        [StructLayout(LayoutKind.Sequential)] struct Key {
            public ushort code, scan;
            public uint flags, time;
            public UIntPtr extra;
        }
        [StructLayout(LayoutKind.Explicit)] struct Data {
            [FieldOffset(0)] public Pointer pointer;
            [FieldOffset(0)] public Key key;
        }
        [StructLayout(LayoutKind.Sequential)] struct Event { public uint type; public Data data; }
        [StructLayout(LayoutKind.Sequential)] struct Point { public int x,y; }
        [StructLayout(LayoutKind.Sequential)] struct ThreadInfo {
            public uint size,flags;
            public IntPtr active,focus,capture,menu,move,caret;
            public int left,top,right,bottom;
        }
        [DllImport("user32.dll", SetLastError=true)] static extern uint SendInput(uint count, Event[] events, int size);
        [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
        [DllImport("user32.dll")] static extern bool GetCursorPos(out Point pt);
        [DllImport("user32.dll")] static extern bool GetGUIThreadInfo(uint thread, ref ThreadInfo info);
        [DllImport("user32.dll")] static extern int GetSystemMetrics(int index);
        [DllImport("user32.dll", SetLastError=true)] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr value);

        static void Foreground(IntPtr window, uint pid) {
            uint owner;
            if (!IfwObservedWindow.OnInputDesktop() || IfwObservedWindow.GetForegroundWindow() != window ||
                    IfwObservedWindow.GetWindowThreadProcessId(window, out owner) == 0 || owner != pid)
                throw new InvalidOperationException("The subject does not own foreground on the input desktop");
        }

        // Check the full crop or gesture path, including any window overlapping its middle.
        public static void RequireRegion(IntPtr window, uint pid, int x, int y, int width, int height) {
            Foreground(window, pid);
            if (width < 1 || width > 1024 || height < 1 || height > 128)
                throw new ArgumentOutOfRangeException("width", "Unexpected filename bounds");
            for (int j = 0; j < height; ++j)
                for (int i = 0; i < width; ++i)
                    if (!IfwObservedWindow.SubjectAt(window, pid, x+i, y+j))
                        throw new InvalidOperationException("A filename point does not hit the owned subject");
        }

        static void RequireReleased() {
            foreach (int key in new[] {1, 2, 4, 5, 6, 0x10, 0x11, 0x12, 0x5b, 0x5c})
                if ((GetAsyncKeyState(key) & 0x8000) != 0)
                    throw new InvalidOperationException("A real mouse button or keyboard modifier is held");
        }
        static uint Submit(params Event[] events) {
            int size = Marshal.SizeOf(typeof(Event));
            if (size != 40) throw new InvalidOperationException("Unexpected 64-bit INPUT size");
            return SendInput((uint)events.Length, events, size);
        }

        static Event Keyboard(ushort code, uint flags) {
            return new Event { type=1, data=new Data { key=new Key { code=code, flags=flags } } };
        }

        public static void Press(IntPtr window, uint pid, string name) {
            ushort code;
            switch (name) {
                case "Right": code=0x27; break;
                case "Left": code=0x25; break;
                case "Delete": code=0x2e; break;
                case "Tab": code=0x09; break;
                default: throw new ArgumentException("Unexpected filename key");
            }
            Foreground(window,pid);
            RequireReleased();
            uint extended = code == 0x09 ? 0u : 1u;
            var up = Keyboard(code, extended | 2u);
            uint sent=Submit(Keyboard(code,extended),up);
            if (sent == 2) return;
            int error=Marshal.GetLastWin32Error();
            if (sent == 1 && IfwObservedWindow.GetForegroundWindow() == window) Submit(up);
            throw new Win32Exception(error,"Incomplete native key");
        }

        static Event Mouse(uint flags, int x, int y) {
            return new Event { data=new Data { pointer=new Pointer { flags=flags, x=x, y=y } } };
        }

        static int Absolute(int coordinate, int origin, int span) {
            long at = (long)coordinate - origin;
            if (span < 1 || at < 0 || at >= span) throw new InvalidOperationException("Point outside the virtual desktop");
            // Aim at the pixel center in the Win32 [0, 65535] absolute virtual-desktop space.
            return (int)(((2 * at + 1) * 65536) / (2L * span));
        }

        public static void Drag(IntPtr window, uint pid, int x0, int x1, int y) {
            if (x0 >= x1) throw new ArgumentException("Drag endpoints must span the character");
            RequireRegion(window, pid, x0, y, x1-x0+1, 1);
            int origin = GetSystemMetrics(76), width = GetSystemMetrics(78);
            int sy = Absolute(y, GetSystemMetrics(77), GetSystemMetrics(79));
            uint move = 0x8000 | 0x4000 | 0x2000 | 1;  // absolute, virtual desktop, no coalescing, move
            RequireReleased();
            MoveOwned(window,pid,move,Absolute(x0,origin,width),sy,x0,y);
            if (Submit(Mouse(2,0,0)) != 1) throw new Win32Exception(Marshal.GetLastWin32Error(),"Mouse down");
            try {
                // egui resolves the anchor and drag extent on separate rendered passes.
                System.Threading.Thread.Sleep(100);
                RequireRegion(window,pid,x0,y,x1-x0+1,1);
                MoveOwned(window,pid,move,Absolute(x1,origin,width),sy,x1,y);
                System.Threading.Thread.Sleep(100);
            } finally {
                uint owner;
                uint thread=IfwObservedWindow.GetWindowThreadProcessId(window,out owner);
                var info=new ThreadInfo { size=(uint)Marshal.SizeOf(typeof(ThreadInfo)) };
                Point p;
                bool capture=thread!=0 && GetGUIThreadInfo(thread,ref info) && info.capture==window;
                bool at=IfwObservedWindow.GetForegroundWindow()==window && GetCursorPos(out p) &&
                    IfwObservedWindow.SubjectAt(window,pid,p.x,p.y);
                if (owner!=pid || !IfwObservedWindow.OnInputDesktop() || !(capture || at))
                    throw new InvalidOperationException("Could not verify the target of the owned button release");
                if (Submit(Mouse(4,0,0))!=1) throw new Win32Exception(Marshal.GetLastWin32Error(),"Mouse up");
            }
        }
        static void MoveOwned(IntPtr window,uint pid,uint flags,int sx,int sy,int x,int y) {
            RequireRegion(window,pid,x,y,1,1);
            if (Submit(Mouse(flags,sx,sy))!=1) throw new Win32Exception(Marshal.GetLastWin32Error(),"Pointer move");
            Point p;
            for (int i=0; i<25; ++i) {
                if (GetCursorPos(out p) && p.x==x && p.y==y) {
                    RequireRegion(window,pid,x,y,1,1);
                    return;
                }
                System.Threading.Thread.Sleep(4);
            }
            throw new InvalidOperationException("Pointer did not reach the requested subject pixel");
        }
    }
}
