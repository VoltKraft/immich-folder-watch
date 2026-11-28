// Resolve the per-run icon button through the original Explorer toolbar's MSAA client.
using System;
using System.Runtime.InteropServices;
using System.Text;
using Accessibility;

public sealed class IfwTrayButton {
    [StructLayout(LayoutKind.Sequential)] struct Point { public int x, y; }
    [DllImport("oleacc")] static extern int AccessibleObjectFromPoint(Point p,
        [MarshalAs(UnmanagedType.Interface)] out IAccessible acc, [MarshalAs(UnmanagedType.Struct)] out object child);
    [DllImport("oleacc")] static extern int AccessibleObjectFromWindow(IntPtr hwnd, uint objectId, ref Guid iid,
        [MarshalAs(UnmanagedType.Interface)] out IAccessible client);
    [DllImport("oleacc")] static extern int WindowFromAccessibleObject([MarshalAs(UnmanagedType.Interface)] IAccessible acc, out IntPtr hwnd);
    [DllImport("oleacc")] static extern int AccessibleChildren([MarshalAs(UnmanagedType.Interface)] IAccessible client,
        int start, int count, [Out, MarshalAs(UnmanagedType.LPArray, ArraySubType=UnmanagedType.Struct, SizeParamIndex=2)] object[] children, out int obtained);
    [DllImport("user32", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr hwnd, StringBuilder name, int size);

    readonly IAccessible acc;
    long originalHit;
    int[] originalRect;
    int pointX, pointY;
    string expectedLabel;
    public readonly int childId;
    public int pointChildId, hitTestChildId, childCount, state;
    public int[] bounds;
    IfwTrayButton(IAccessible owner, int child) { acc=owner; childId=child; }

    static void Require(bool ok, string message) { if (!ok) throw new InvalidOperationException(message); }
    static IfwTrayButton Child(IAccessible owner, object hit) {
        if (hit is int && (int)hit >= 0) return new IfwTrayButton(owner,(int)hit);
        if (hit is IAccessible) return new IfwTrayButton((IAccessible)hit,0);
        throw new InvalidOperationException("MSAA did not identify a toolbar child");
    }
    void Check(IntPtr hwnd, string label, int[] rect, int x, int y) {
        IntPtr window;
        Require(WindowFromAccessibleObject(acc,out window)==0 && window==hwnd,
                "MSAA did not map the button to the original Explorer hit HWND");
        Require(acc.get_accName(childId)==label && Equals(acc.get_accRole(childId),0x2b),
                "MSAA did not identify the exact named push button");
        object flags=acc.get_accState(childId);
        Require(flags is int, "Missing MSAA button state");
        state=(int)flags;
        // STATE_SYSTEM_UNAVAILABLE, INVISIBLE and OFFSCREEN.
        Require((state & 0x18001)==0 && !String.IsNullOrWhiteSpace(acc.get_accDefaultAction(childId)),
                "The exact MSAA button is unavailable, offscreen or has no default action");
        int left,top,width,height;
        acc.accLocation(out left,out top,out width,out height,childId);
        long right=(long)left+width,bottom=(long)top+height;
        Require(width>0 && height>0 && rect[0]<=left && left<=x && x<right && right<=rect[2] &&
                rect[1]<=top && top<=y && y<bottom && bottom<=rect[3], "MSAA bounds differ from the observed Shell icon");
        bounds=new int[]{left,top,(int)right,(int)bottom};
    }
    bool SameButton(IfwTrayButton other) {
        return (childId==0 || other.childId==0 || childId==other.childId) && state==other.state &&
            System.Collections.StructuralComparisons.StructuralEqualityComparer.Equals(bounds,other.bounds);
    }
    public static IfwTrayButton At(long hit, int[] rect, int x, int y, string label) {
        var hwnd=new IntPtr(hit);
        var cls=new StringBuilder(80);
        Require(GetClassName(hwnd,cls,cls.Capacity)>0 && cls.ToString()=="ToolbarWindow32",
                "The original Explorer hit is not a classic notification toolbar");
        var iid=typeof(IAccessible).GUID;
        IAccessible client,point; object id; IntPtr window;
        Require(AccessibleObjectFromWindow(hwnd,0xfffffffc,ref iid,out client)==0 && client!=null,
                "The original toolbar did not expose an MSAA client");
        Require(WindowFromAccessibleObject(client,out window)==0 && window==hwnd,"MSAA toolbar HWND changed");
        Require(AccessibleObjectFromPoint(new Point{x=x,y=y},out point,out id)==0 && point!=null && id is int,
                "MSAA point lookup did not return an accessible child");
        var atPoint=Child(point,id);
        atPoint.Check(hwnd,label,rect,x,y);
        var atHit=Child(client,client.accHitTest(x,y));
        atHit.Check(hwnd,label,rect,x,y);
        Require(atPoint.SameButton(atHit),"MSAA point and toolbar hit-test results differ");
        int n=client.accChildCount, obtained;
        Require(n>0 && n<=128,"Unbounded or empty MSAA toolbar item set");
        var children=new object[n];
        Require(AccessibleChildren(client,0,n,children,out obtained)==0 && obtained==n && client.accChildCount==n,
                "The original toolbar item set changed during MSAA enumeration");
        IfwTrayButton selected=null;
        foreach (object value in children) {
            var child=Child(client,value);
            if (child.acc.get_accName(child.childId)!=label) continue;
            Require(selected==null,"Multiple MSAA toolbar items carry the fixture name");
            child.Check(hwnd,label,rect,x,y);
            Require(atPoint.SameButton(child) && atHit.SameButton(child),"MSAA named child differs from the physical hit");
            selected=child;
        }
        Require(selected!=null && client.accChildCount==n,"Missing unique named MSAA toolbar item");
        selected.pointChildId=atPoint.childId; selected.hitTestChildId=atHit.childId; selected.childCount=n;
        selected.originalHit=hit; selected.originalRect=(int[])rect.Clone(); selected.pointX=x; selected.pointY=y; selected.expectedLabel=label;
        return selected;
    }
    public void Recheck() {
        var expectedBounds=bounds;
        int expectedState=state;
        Check(new IntPtr(originalHit),expectedLabel,originalRect,pointX,pointY);
        Require(state==expectedState && System.Collections.StructuralComparisons.StructuralEqualityComparer.Equals(bounds,expectedBounds),
                "The selected MSAA button changed before its default action");
    }
    public void Invoke() { acc.accDoDefaultAction(childId); }
}
