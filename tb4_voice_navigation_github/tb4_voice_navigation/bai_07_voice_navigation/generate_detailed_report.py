#!/usr/bin/env python3
"""Build an illustrated Vietnamese Word report using real project data/logs.

Run with system Python (python-docx, matplotlib, scipy, opencv, PyYAML).
No simulation is launched and no microphone audio is recorded.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import textwrap

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
from scipy.signal import butter, sosfreqz
import yaml
from docx import Document
from docx.shared import Cm, Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "report_assets"
OUTPUT = ROOT / "Bao_cao_chi_tiet_Bai_07.docx"
BLUE = "194D72"


def parse_log(path):
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.search(r"\[([0-9]+\.[0-9]+)\].*?\[voice_navigation\]: (\{.*\})", line)
        if match:
            events.append(dict(time=float(match[1]), **json.loads(match[2])))
    return events


def read_missions(events):
    missions, current = [], None
    for event in events:
        if event["state"] == "ROUTE":
            current = dict(start=event["time"], command=event["command"], route=event["route"])
        if current and event["state"] in {"SUCCEEDED", "STOPPED", "FAILED", "REJECTED"}:
            current.update(end=event["time"], state=event["state"], duration=event["time"]-current["start"])
            missions.append(current)
            current = None
    return missions


def savefig(name):
    plt.savefig(ASSETS / name, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close()


def box(ax, xy, width, height, label, color="#e4eff7", fontsize=10):
    x, y = xy
    ax.add_patch(FancyBboxPatch((x,y), width,height, boxstyle="round,pad=0.02", facecolor=color, edgecolor="#315d7c", linewidth=1.2))
    ax.text(x+width/2, y+height/2, label, ha="center", va="center", fontsize=fontsize)


def arrow(ax, start, end, label=None):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=13, color="#315d7c", linewidth=1.4))
    if label:
        ax.text((start[0]+end[0])/2, (start[1]+end[1])/2+.12, label, ha="center", fontsize=8)


def illustrations(data, events, missions):
    ASSETS.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family":"DejaVu Sans", "font.size":10})
    original = cv2.imread(str(ROOT / "maps/original.pgm"),0)
    segmented = cv2.cvtColor(cv2.imread(str(ROOT / "maps/segmented_map.png")),cv2.COLOR_BGR2RGB)
    fig, axes = plt.subplots(1,2,figsize=(9,7))
    for ax, im, title in zip(axes,[original,segmented],["Bản đồ gốc Occupancy Grid", "Ba vùng chức năng và đích A/B/C"]):
        ax.imshow(im,cmap="gray",vmin=0,vmax=255); ax.set_title(title); ax.axis("off")
    savefig("01_maps.png")

    fig, ax = plt.subplots(figsize=(11,5.3)); ax.set(xlim=(0,12),ylim=(0,6)); ax.axis("off")
    box(ax,(.2,3.6),2,1.2,"Micro laptop\nALSA / PipeWire")
    box(ax,(3.2,3.6),2.3,1.2,"PCM16 mono, 16 kHz\nHigh-pass 150 Hz\nVosk + grammar")
    box(ax,(6.6,3.6),2.2,1.2,"Chuẩn hóa câu\nKiểm tra tên vùng\nTạo chuỗi đích")
    box(ax,(9.6,3.6),2.1,1.2,"Nav2 action\nNavigateToPose")
    for a,b in [((2.2,4.2),(3.2,4.2)),((5.5,4.2),(6.6,4.2)),((8.8,4.2),(9.6,4.2))]:arrow(ax,a,b)
    box(ax,(6.6,1),2.2,1.2,"regions.yaml\nID, alias, goal, hash", "#fff1cd")
    box(ax,(9.6,1),2.1,1.2,"TurtleBot 4\nGazebo + AMCL\nCostmap / LiDAR", "#dcefdc")
    box(ax,(.5,1),4.9,1.2,"Giám sát: /voice_nav/status + transcript\nRViz: nhãn vùng, thứ tự đích, đường Nav2")
    arrow(ax,(7.7,2.2),(7.7,3.6));arrow(ax,(10.65,3.6),(10.65,2.2))
    arrow(ax,(9.6,1.6),(5.4,1.6),"feedback / result")
    savefig("02_architecture.png")

    from map_tools import OccupancyMap, largest_component
    occ=OccupancyMap(ROOT/"maps/original.yaml")
    mask=largest_component(occ.free & (occ.clearance>=data["clearance_m"]))
    labels=cv2.imread(str(ROOT/"maps/labels.png"),cv2.IMREAD_UNCHANGED)
    fig,axes=plt.subplots(1,3,figsize=(10,6.2))
    for ax,im,title in zip(axes,[occ.free,mask,labels],["(a) Ô trống theo YAML","(b) Clearance + liên thông","(c) Phân vùng BFS"]):
        ax.imshow(im,cmap="viridis" if im is labels else "gray");ax.set_title(title,fontsize=10);ax.axis("off")
    savefig("03_segmentation.png")

    fig,ax=plt.subplots(figsize=(9,4));ax.set(xlim=(0,11),ylim=(0,5));ax.axis("off")
    box(ax,(.3,1.6),2.5,1.5,"Pixel ảnh (u, v)\nGốc trên trái\nv tăng xuống dưới")
    box(ax,(4,1.6),2.5,1.5,"Tâm ô local\nx = (u + 0,5)r\ny = (H − v − 0,5)r")
    box(ax,(7.7,1.6),2.9,1.5,"Tọa độ frame map\nQuay theo origin yaw\nCộng origin x, y")
    arrow(ax,(2.8,2.35),(4,2.35));arrow(ax,(6.5,2.35),(7.7,2.35))
    ax.text(5.5,.65,"Ví dụ A: pixel (238, 410) → map (−3,158 m; 3,161 m)",ha="center",fontsize=11)
    savefig("04_coordinates.png")

    fig,ax=plt.subplots(figsize=(9,3.5))
    frequencies=np.geomspace(10,4000,1500)
    f,h=sosfreqz(butter(4,150,fs=16000,btype="highpass",output="sos"),worN=frequencies,fs=16000)
    ax.semilogx(f,20*np.log10(np.maximum(abs(h),1e-8)),color="#246b94",lw=2)
    ax.axvline(35.3,color="#bd5735",ls="--",label="Đỉnh tiếng ù đo được: 35,3 Hz")
    ax.axvline(150,color="#408049",ls=":",label="Tần số cắt: 150 Hz")
    ax.set(xlabel="Tần số (Hz)",ylabel="Độ lợi (dB)",ylim=(-85,5),title="Đáp tuyến bộ lọc dùng trong mã nguồn — không phải phổ thu âm")
    ax.grid(True,alpha=.25);ax.legend(fontsize=8);savefig("05_filter.png")

    fig,ax=plt.subplots(figsize=(11,4.6));ax.set(xlim=(0,12),ylim=(0,5));ax.axis("off")
    for xy,w,h,label,color in [((.1,3),2,1,"READY / IDLE","#e4eff7"),((3,3),2.3,1,"Kiểm tra toàn câu\nROUTE","#e4eff7"),((6.2,3),2.3,1,"NAVIGATING\nGửi một đích","#fff1cd"),((9.5,3),2.3,1,"ARRIVED\nĐích thành công","#dcefdc"),((3,.7),2.3,1,"INVALID_COMMAND\nKhông gửi goal","#f6dddd"),((6.2,.7),2.3,1,"CANCELING\nSTOPPED / FAILED","#f6dddd"),((9.5,.7),2.3,1,"SUCCEEDED\nHết chuỗi đích","#dcefdc")]:box(ax,xy,w,h,label,color,9)
    for a,b in [((2.1,3.5),(3,3.5)),((5.3,3.5),(6.2,3.5)),((8.5,3.5),(9.5,3.5)),((4.15,3),(4.15,1.7)),((7.35,3),(7.35,1.7)),((10.65,3),(10.65,1.7))]:arrow(ax,a,b)
    arrow(ax,(10.65,4),(7.35,4),"còn đích: chỉ gửi sau thành công")
    savefig("06_states.png")

    fig,ax=plt.subplots(figsize=(10,4))
    colors=["#287c83" if m["state"]=="SUCCEEDED" else "#c28338" for m in missions]
    ax.bar(range(1,len(missions)+1),[m["duration"] for m in missions],color=colors)
    for i,m in enumerate(missions,1):
        ax.text(i,m["duration"]+3,f"{m['route'][0]}\n{m['duration']:.1f}s",ha="center",fontsize=8)
    ax.set(xlabel="Lượt điều hướng trong phiên giọng nói",ylabel="Thời gian theo log (giây)",ylim=(0,220),xticks=list(range(1,len(missions)+1)),title="Dữ liệu thực tế: xanh = hoàn thành; cam = người dùng hủy")
    ax.grid(axis="y",alpha=.2);savefig("07_missions.png")

    # Actual log excerpts typeset as a figure, explicitly not a UI screenshot.
    lines=["TRÍCH LOG THỰC TẾ — không phải ảnh chụp giao diện",
           "ASR (0.99): đi đến phòng học",
           "ROUTE: A → NAVIGATING → ARRIVED A → SUCCEEDED",
           "Thời gian từ ROUTE đến SUCCEEDED: 40,16 giây",
           "",
           "ASR (0.87): đi đến phòng thí nghiệm",
           "ROUTE: B → ARRIVED B → SUCCEEDED (179,26 giây)",
           "",
           "ASR (0.77): dừng lại",
           "CANCELING → STOPPED (khoảng 26 ms từ lúc node nhận hủy)",
           "Lưu ý: 26 ms không bao gồm thời gian nói/ASR hoặc đo dừng cơ khí."]
    fig,ax=plt.subplots(figsize=(10,4.5));ax.set_facecolor("#152c3c");fig.patch.set_facecolor("#152c3c")
    ax.axis("off")
    for i,line in enumerate(lines):ax.text(.03,.94-i*.083,line,transform=ax.transAxes,color="#f0f6fb",fontsize=10,va="top")
    plt.savefig(ASSETS/"08_evidence.png",dpi=190,bbox_inches="tight",facecolor=fig.get_facecolor());plt.close()


class Report:
    def __init__(self):
        self.doc=Document(); self.figure_index=0
        s=self.doc.sections[0]
        s.page_height=Cm(29.7);s.page_width=Cm(21)
        s.top_margin=Cm(1.9);s.bottom_margin=Cm(1.8);s.left_margin=Cm(2.2);s.right_margin=Cm(1.8)
        normal=self.doc.styles["Normal"]
        normal.font.name="Times New Roman";normal.font.size=Pt(12)
        normal.paragraph_format.line_spacing=1.12
        normal.paragraph_format.space_after=Pt(7)
        for name,size in [("Title",23),("Heading 1",17),("Heading 2",13),("Heading 3",12)]:
            self.doc.styles[name].font.name="DejaVu Sans"
            self.doc.styles[name].font.size=Pt(size)
            self.doc.styles[name].font.color.rgb=RGBColor.from_string(BLUE)
        self.doc.styles["Caption"].font.name="Times New Roman"
        self.doc.styles["Caption"].font.size=Pt(10)
        h=s.header.paragraphs[0];h.text="BÀI THỰC HÀNH 7  |  TURTLEBOT 4 • VOICE NAVIGATION"
        h.runs[0].font.size=Pt(8);h.runs[0].font.color.rgb=RGBColor.from_string(BLUE)
        footer=s.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
        footer.add_run("Báo cáo chi tiết  •  Trang ").font.size=Pt(9)
        field=OxmlElement("w:fldSimple");field.set(qn("w:instr"),"PAGE");footer._p.append(field)
        self.doc.core_properties.title="Bài 7 — Phân vùng bản đồ và điều hướng robot bằng giọng nói"
        self.doc.core_properties.subject="Triển khai, kiểm chứng, sự cố và khắc phục trên TurtleBot 4 Simulation"
        self.doc.core_properties.author=""
        self.doc.core_properties.created=datetime.now(timezone.utc)
        self.doc.core_properties.modified=datetime.now(timezone.utc)
        self.doc.core_properties.language="vi-VN"
        self.doc.core_properties.comments="Báo cáo tạo từ mã nguồn, bản đồ và log thực nghiệm của bài 7."

    def p(self,text):
        p=self.doc.add_paragraph(text);p.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY;return p

    def heading(self,text,level=2):self.doc.add_heading(text,level)

    def page(self,title):
        self.doc.add_page_break();self.heading(title,1)

    def table(self,headers,rows):
        t=self.doc.add_table(rows=1, cols=len(headers));t.style="Light Shading Accent 1"
        for c,h in zip(t.rows[0].cells,headers):c.text=str(h)
        for row in rows:
            cells=t.add_row().cells
            for c,v in zip(cells,row):c.text=str(v)
        for row in t.rows:
            prop=row._tr.get_or_add_trPr();prop.append(OxmlElement("w:cantSplit"))
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.space_after=Pt(4)
                    for run in p.runs:run.font.size=Pt(10)
        for c in t.rows[0].cells:
            for run in c.paragraphs[0].runs:run.bold=True
        self.doc.add_paragraph()

    def code(self,text):
        p=self.doc.add_paragraph()
        p.paragraph_format.space_before=Pt(4);p.paragraph_format.space_after=Pt(8)
        p.paragraph_format.line_spacing=1
        shade=OxmlElement("w:shd");shade.set(qn("w:fill"),"EDF2F6");p._p.get_or_add_pPr().append(shade)
        for i,line in enumerate(text.strip().splitlines()):
            if i:p.add_run().add_break()
            run=p.add_run(line);run.font.name="DejaVu Sans Mono";run.font.size=Pt(8)

    def fig(self,file,caption,width=6.45):
        p=self.doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(ASSETS/file),width=Inches(width))
        self.figure_index+=1
        p=self.doc.add_paragraph(f"Hình {self.figure_index}. {caption}",style="Caption")
        p.alignment=WD_ALIGN_PARAGRAPH.CENTER


def main():
    data=yaml.safe_load((ROOT/"maps/regions.yaml").read_text())
    events=parse_log(ROOT/"results/voice_session_navigation.log")
    missions=read_missions(events)
    (ROOT/"results/voice_session_summary.json").write_text(json.dumps(missions,ensure_ascii=False,indent=2))
    illustrations(data,events,missions)
    r=Report()

    # Cover
    r.doc.add_paragraph("BÁO CÁO THỰC HÀNH",style="Subtitle")
    r.doc.add_heading("BÀI THỰC HÀNH 7",0)
    r.doc.add_heading("PHÂN VÙNG BẢN ĐỒ VÀ ĐIỀU HƯỚNG ROBOT BẰNG GIỌNG NÓI",1)
    r.p("TurtleBot 4 Simulation • ROS 2 Jazzy • Gazebo Harmonic")
    r.doc.add_paragraph("Sinh viên: .............................................................\nMã sinh viên: .........................................................\nLớp / Nhóm: ..........................................................\nGiảng viên hướng dẫn: ...........................................")
    r.fig("01_maps.png","Bản đồ gốc và ba vùng chức năng sử dụng trong bài thực hành.",5.1)
    r.p("Ngày lập báo cáo: 06/11/2026. Thời lượng theo đề bài: 01 tuần. Báo cáo này trình bày chi tiết cách triển khai, dữ liệu kiểm chứng và quá trình xử lý sự cố; bổ sung cho bản báo cáo PDF ngắn 1–2 trang của yêu cầu nộp bài.")
    contents_anchor=r.doc.add_paragraph()

    r.page("1. Tóm tắt, mục tiêu và phạm vi")
    r.p("Bài thực hành xây dựng một chuỗi xử lý thống nhất từ câu nói tiếng Việt đến chuyển động tự hành của TurtleBot 4 trong mô phỏng. Bản đồ 2D đã tạo được chia thành ít nhất ba vùng, mỗi vùng có tên và một pose đích hợp lệ. Bộ nhận dạng giọng nói chuyển âm thanh thành văn bản; bộ phân tích xác định hành trình; ROS 2 node lần lượt gửi các đích đến Nav2.")
    r.p("Điểm chính của giải pháp là dùng các thành phần có thể kiểm tra độc lập: phân vùng bản đồ không cần mở Gazebo; parser không cần micro; giao tiếp action có thể thử với Nav2 giả lập; cuối cùng mới ghép micro, localization và điều hướng trên Gazebo. Cách tách này giúp xác định lỗi xảy ra ở nhận dạng, phân tích câu hay thực thi robot.")
    r.table(["Yêu cầu", "Giải pháp", "Minh chứng"],[
        ["Ít nhất 3 vùng có nhãn","Geodesic Voronoi + YAML A/B/C","Bản đồ phân vùng, labels.png, regions.yaml"],
        ["Ít nhất 3 câu giọng nói","Phòng học, phòng thí nghiệm, hành lang","Log ASR thực tế có cả ba tên"],
        ["Điều hướng đúng đích","Action NavigateToPose, Nav2","Log ARRIVED/SUCCEEDED ở A và B"],
        ["Vùng không tồn tại","Kiểm tra toàn bộ câu trước khi gửi goal","Test parser/action và lệnh vùng D"],
        ["Từ A đến B khi đang nơi khác","Gửi A rồi B, chờ thành công mỗi chặng","Test ROS action theo thứ tự"],
        ["Dừng đang thực hiện","Hủy goal, xóa các điểm còn lại","Log CANCELING → STOPPED bằng giọng nói"]])
    r.heading("Cách hiểu kết quả")
    r.p("Người dùng đã xác nhận hệ thống hoạt động ổn định sau khi chỉnh sửa. Báo cáo đối chiếu nhận xét đó với log: A và B có kết quả đến đích thành công; các lệnh đi C trong phiên được lưu đã bị người dùng chủ động hủy, vì vậy không coi các lượt này là bằng chứng hoàn thành tại C. Không suy ra tỷ lệ nhận dạng hoặc tỷ lệ tránh vật cản từ một vài lần demo.")
    r.heading("Nội dung báo cáo")
    r.p("Các phần tiếp theo trình bày môi trường và kiến trúc; xử lý bản đồ và tọa độ; semantic mapping; nhận dạng và xử lý âm thanh; parser và action; hướng dẫn chạy; kiểm thử; kết quả giọng nói thực tế; các lỗi đã gặp, nguyên nhân và cách khắc phục; giới hạn và hướng phát triển.")

    r.page("2. Môi trường, cấu trúc và kiến trúc")
    r.table(["Thành phần", "Cấu hình sử dụng"],[
        ["Hệ điều hành / ROS","Ubuntu 24.04; ROS 2 Jazzy; Python 3.12"],
        ["Mô phỏng","Gazebo Harmonic; TurtleBot 4; world warehouse"],
        ["Bản đồ","PGM 605 × 975 pixel; resolution 0,05 m/pixel"],
        ["Điều hướng","Nav2 + AMCL; frame map; NavigateToPose"],
        ["Middleware","rmw_fastrtps_cpp, thống nhất giữa các terminal"],
        ["ASR","Vosk 0.3.45; vosk-model-small-vn-0.4; offline"],
        ["Thu âm / xử lý","ALSA arecord qua PipeWire; SciPy; PCM16 mono 16 kHz"]])
    r.fig("02_architecture.png","Kiến trúc triển khai theo mã nguồn; các khối là sơ đồ giải thích, không phải ảnh chụp màn hình.")
    r.p("Thư mục bài tập là bai_07_voice_navigation; launch mô phỏng và cấu hình Nav2 được tái sử dụng từ package tb4_assignment. Node nhận giọng nói và node điều hướng là hai chương trình riêng, trao đổi qua std_msgs/String. Không cần sửa launch gz_ogre2 để thêm parser hoặc ASR.")
    r.p("File map_tools.py phụ trách hình học, clearance và tính nhất quán bản đồ; commands.py chứa ngữ pháp lệnh; speech.py xử lý âm thanh và Vosk; voice_input.py xuất transcript/lệnh; navigation_node.py quản lý action và marker. Việc phân tách này giúp sửa ASR mà không làm thay đổi thuật toán điều hướng.")

    r.page("3. Bản đồ đầu vào và biểu diễn dữ liệu")
    r.p("Bản đồ gốc lấy từ src/tb4_assignment/maps/final_map.pgm và final_map.yaml, được sao chép sang maps/original.pgm và original.yaml để giữ sản phẩm bài 7 độc lập về dữ liệu. Khi dùng bản đồ khác phải truyền đúng map cho cả Nav2 và công cụ phân vùng.")
    r.code("image: original.pgm\nmode: trinary\nresolution: 0.05\norigin: [-15.083, -25.064, 0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196")
    r.p("Ảnh PGM là ma trận cường độ, còn bản đồ ROS là dữ liệu không gian. Với negate=0, xác suất chiếm chỗ được tính là 1 − intensity/255. Chương trình chọn ô free khi xác suất này nhỏ hơn free_thresh. Những ô không được xác nhận là free, gồm vật cản và unknown, đều không được sử dụng để đặt đích.")
    r.p("Bản đồ đang dùng thể hiện một kho hàng với kệ và các khoảng đi lại; nó không cung cấp sẵn chức năng phòng. Vì vậy ba vùng A/B/C là phân vùng chức năng. Các tên “phòng học”, “phòng thí nghiệm”, “hành lang” là nhãn ngữ nghĩa gán để minh họa tương tác, không phải kết quả máy tự nhận biết loại phòng.")
    r.table(["Sản phẩm bản đồ", "Ý nghĩa"],[
        ["original.pgm + original.yaml","Dữ liệu gốc và phép đổi pixel ↔ ROS"],
        ["labels.png","Ảnh uint16: 0 là ngoài vùng; 1/2/3 tương ứng A/B/C"],
        ["segmented_map.png","Bản tô màu có chữ A/B/C và điểm đích để xem trực quan"],
        ["regions.yaml","Tên, alias, pixel, pose x/y/yaw, diện tích, clearance và hash"]])
    r.p("Ảnh nhãn không được thay thế ảnh Occupancy Grid của Nav2: nhãn vùng phục vụ hiểu lệnh, còn map/costmap phục vụ lập đường. Nếu đưa nhầm ảnh tô màu vào map server, ý nghĩa xác suất chiếm chỗ sẽ không còn đúng.")

    r.page("4. Thuật toán phân vùng bản đồ")
    r.fig("03_segmentation.png","Các bước xử lý từ sàn free đến vùng đi được có clearance và ảnh nhãn.")
    r.heading("4.1. Chuẩn bị miền có thể đặt đích")
    r.p("Đầu tiên đọc ảnh grayscale và YAML, kiểm tra resolution/origin hợp lệ. Sau threshold, distance transform đo khoảng cách từ tâm mỗi ô free đến miền không free. Ảnh được padding để cạnh ảnh cũng được coi là giới hạn. Chỉ giữ các ô có clearance ít nhất 0,35 m; tiếp theo chọn thành phần liên thông lớn nhất theo bốn hướng.")
    r.heading("4.2. Seed và BFS đa nguồn")
    r.p("Seed đầu được chọn tại nơi có clearance lớn. Các seed tiếp theo lấy theo chiến lược farthest-point dựa trên khoảng cách Euclid đến seed đã chọn, nhưng vẫn nằm trong cùng miền hợp lệ. Từ các seed, BFS đa nguồn lan theo bốn hướng; một ô được gán nhãn cho nguồn đến trước. Do chỉ lan trong mask, nhãn không xuyên tường hoặc ô unknown. Đây là geodesic Voronoi trên lưới, không phải watershed phát hiện phòng.")
    r.heading("4.3. Chọn điểm đích và đặc điểm kết quả")
    r.p("Sau khi có nhãn, distance transform trong từng vùng giúp chọn điểm nằm sâu bên trong vùng. Cách này tránh nhược điểm centroid của vùng lõm có thể rơi vào tường. Các seed và đích cuối không bắt buộc trùng nhau. Vùng A lớn hơn B/C do bố cục kho và vị trí seed; thuật toán không tối ưu diện tích các vùng bằng nhau.")
    r.p("Có thể truyền JSON seed thủ công bằng --seeds. Tất cả seed phải khác nhau và thuộc miền đủ clearance. Khi tạo lại phân vùng, regions.yaml bị ghi đè; cần bảo toàn các alias đã tùy chỉnh. Clearance là điều kiện hình học tĩnh cho tâm robot, không thay thế footprint/inflation và costmap của Nav2.")

    r.page("5. Chuyển đổi tọa độ và kiểm tra đích")
    r.fig("04_coordinates.png","Phép đổi tọa độ từ tâm pixel ảnh sang frame map.")
    r.p("Ảnh dùng gốc trên trái, trục v hướng xuống; bản đồ ROS dùng trục y hướng lên. Với ảnh cao H và độ phân giải r, tính tọa độ local tại tâm ô: x_local=(u+0,5)r và y_local=(H−v−0,5)r. Sau đó quay điểm local theo yaw của origin và cộng tịnh tiến origin x/y.")
    r.code("x_map = origin_x + cos(yaw)*x_local - sin(yaw)*y_local\ny_map = origin_y + sin(yaw)*x_local + cos(yaw)*y_local")
    r.table(["Vùng", "Pixel (u,v)", "x (m)", "y (m)", "yaw"],[
        [g["id"],str(tuple(g["pixel"])),f"{g['goal']['x']:.3f}",f"{g['goal']['y']:.3f}","0 rad"] for g in data["regions"]])
    r.p("Ví dụ A: u=238, v=410, H=975, r=0,05. Khi yaw=0, x=−15,083+(238+0,5)×0,05=−3,158 m; y=−25,064+(975−410−0,5)×0,05=3,161 m. Góc yaw=0 tạo quaternion z=0, w=1 cho các đích hiện tại.")
    r.p("Khi nạp file vùng, node kiểm tra frame_id=map; các số x/y/yaw hữu hạn; đích thuộc ô free, đủ clearance và nằm trong thành phần chính. Hash SHA-256 của ảnh và metadata phải khớp. Nếu map bị đổi nhưng vùng chưa tạo lại, node từ chối chạy để tránh dùng tọa độ cũ.")
    r.p("Đích hợp lệ trên bản đồ chưa bảo đảm robot hiện tại đi tới được: robot còn cần undock, định vị đúng, TF hợp lệ và một đường đi được planner Nav2 tìm thấy. Chuyển đúng tọa độ và có localization đúng là hai điều kiện riêng biệt.")

    r.page("6. Gắn nhãn ngữ nghĩa và từ điển vùng")
    r.table(["ID", "Tên dùng khi nói", "Tên thay thế", "Diện tích mask"],[
        ["A","phòng học","khu vực A; khu vực một",f"{data['regions'][0]['area_m2']:.2f} m²"],
        ["B","phòng thí nghiệm","khu vực B; bê; khu vực hai",f"{data['regions'][1]['area_m2']:.2f} m²"],
        ["C","hành lang","khu vực C; xê; khu vực ba",f"{data['regions'][2]['area_m2']:.2f} m²"]])
    r.p("ID là khóa ổn định liên kết với pose. Name/aliases là lớp ngôn ngữ để người dùng gọi tên. Nhiều cách nói có thể quy về một ID, nhưng cùng một alias không được trỏ tới hai vùng khác nhau. Diện tích trong bảng tính từ số ô có nhãn nhân r², không phải diện tích kiến trúc toàn bộ phòng hoặc kho.")
    r.code("- id: A\n  name: Khu vực A\n  aliases: [vùng A, phòng học, khu vực một, vùng một]\n  pixel: [238, 410]\n  goal: {x: -3.158, y: 3.161, yaw: 0.0}")
    r.heading("Lý do chuyển sang tên nhiều âm tiết")
    r.p("Trong thử nghiệm, Vosk thường nhận đúng tiền tố “đi đến khu vực” nhưng dao động ở âm cuối A/bê/dê/xê. Tên chữ cái quá ngắn khiến tín hiệu mục tiêu khó phân biệt. Thêm các tên “phòng học”, “phòng thí nghiệm”, “hành lang” tạo nhiều âm tiết và ngữ cảnh khác nhau, trong khi tọa độ đích không đổi. Log sau chỉnh sửa có đủ ba lệnh này với confidence lần lượt 0,99; 0,87; 1,00 ở các lượt đầu rõ ràng.")
    r.p("Sau khi sửa alias phải khởi động lại cả node điều hướng và node ASR: một bên cần nạp lại parser, bên kia cần dựng lại grammar. Nếu dùng --regions cho cấu hình riêng, hai node phải trỏ tới cùng file. Việc đổi alias ở file không tự cập nhật các tiến trình đang chạy.")
    r.p("Tên nhiều âm tiết giúp cải thiện trường hợp thực tế đã gặp, nhưng chưa phải một phép đo WER hay cam kết nhận dạng mọi giọng nói. Không dùng quy tắc sửa “dê” thành A vì có thể khiến câu yêu cầu vùng không tồn tại bị đổi thành một đích có thật.")

    r.page("7. Thu âm và nhận dạng tiếng Việt")
    r.heading("7.1. Luồng âm thanh")
    r.p("arecord thu PCM S16_LE, một kênh, 16 kHz qua thiết bị pipewire. Worker đọc dữ liệu theo chunk, giữ lại byte lẻ nếu có để bảo đảm mẫu 16-bit hoàn chỉnh. Một bộ lọc high-pass xử lý âm thanh trước khi đưa vào KaldiRecognizer của Vosk. Cấu hình micro mặc định của máy là Digital Microphone của laptop; việc phát âm thanh qua tai nghe Baseus không chứng minh âm thanh đang được thu từ micro tai nghe.")
    r.heading("7.2. Grammar và kiểm soát ngoài từ vựng")
    r.p("Ban đầu bộ nhận dạng dùng ngôn ngữ mở và trả nhiều từ ngoài nội dung điều hướng. Bản sửa tạo grammar từ name/aliases, các mẫu đi đến/từ/qua/rồi đến và lệnh dừng/hủy. Grammar giữ [unk] và vùng không tồn tại D/dê để không ép mọi phát âm về A/B/C. Trước khi dựng grammar, bỏ cả câu có từ không có trong vocabulary model; không chỉ bỏ riêng từ đích vì sẽ làm câu bị cụt.")
    r.p("Model small-vn-0.4 có graph HCLr.fst hỗ trợ cấu hình động trong phiên đã kiểm tra. --free-form cho phép quay về bộ từ vựng mở khi chẩn đoán; nếu model không hỗ trợ grammar hoặc thiếu [unk], chương trình báo lỗi rõ ràng.")
    r.heading("7.3. Partial, final và confidence")
    r.p("Partial chỉ phục vụ quan sát, không phát lệnh robot. Chỉ kết quả cuối câu mới được xét. Confidence câu hiện lấy giá trị nhỏ nhất trong các từ và so với ngưỡng 0,65; câu rỗng, có [unk] hoặc thấp ngưỡng không được publish command. Cách lấy minimum khá chặt, có thể loại một câu gần đúng, nhưng tránh dùng phần đích còn chưa chắc chắn để làm robot di chuyển.")
    r.p("Khi thiết bị không gửi âm thanh quá 5 giây, worker báo lỗi thay vì chờ vô hạn. Khi tắt micro, không áp dụng phần FinalResult còn dang dở. Khi mất subscriber điều hướng, lệnh bị bỏ và yêu cầu nói lại sau khi kết nối; không tự chạy một lệnh đã cũ khi node xuất hiện trở lại.")
    r.table(["Log / tùy chọn", "Ý nghĩa"],[
        ["PARTIAL","Văn bản tạm thời, còn có thể đổi ở cuối câu"],
        ["ASR (confidence)","Câu đã chốt và đủ điều kiện gửi"],
        ["AUDIO: Sau lọc","Mức dBFS/clipping của tín hiệu sau bộ lọc"],
        ["--listen-only","Chẩn đoán nhận dạng mà không gửi command robot"],
        ["--audio-level / --highpass 0","Xem mức thu / đối chiếu khi tắt lọc"]])

    r.page("8. Đo tiếng ù và xử lý bão hòa âm thanh")
    r.p("Một lần đo PCM trực tiếp 3 giây cho RMS khoảng −10,2 dBFS, clipping 0,35%, đỉnh năng lượng 35,3 Hz; 92,2% năng lượng nằm dưới 150 Hz. Đây là bằng chứng tiếng ù tần số thấp trong tín hiệu thu. Chưa có phép đo riêng từng nguồn cơ khí nên không khẳng định chắc tiếng đó do quạt, bàn hay một thiết bị cụ thể.")
    r.fig("05_filter.png","Đáp tuyến tính từ đúng cấu hình bộ lọc trong mã nguồn. Đường này là mô hình bộ lọc, không phải phổ ghi âm.")
    r.p("Đã thêm bộ lọc Butterworth high-pass bậc 4, tần số cắt 150 Hz, triển khai bằng second-order sections. Trạng thái sosfilt được giữ qua các chunk, tránh khởi tạo lại bộ lọc ở từng lần đọc gây xung giả. Kiểm thử tín hiệu tổng hợp xác minh giảm thành phần 35 Hz hơn 40 dB và giữ thành phần 500 Hz với suy hao dưới 1 dB.")
    r.table(["Đo đối chiếu trên cùng một đoạn PCM", "Trước lọc", "Sau lọc"],[
        ["RMS", "−12,41 dBFS", "−22,50 dBFS"],
        ["Tỷ lệ mẫu clipping", "khoảng 0,0417%", "0% ở đầu ra lọc"]])
    r.p("Đây là một lần đo khác với phép phân tích phổ ở trên; không gộp các mẫu thành cùng một điều kiện. Giảm RMS sau lọc cho thấy năng lượng thấp tần bị loại, không đồng nghĩa đã đo được mức tăng độ chính xác ASR. Bộ lọc không phục hồi được thông tin đã mất do bão hòa khi thu.")
    r.p("Ở một số lần nói, log sau lọc còn ghi clipping 9,8–10,8%. Nguồn thu mặc định được giảm volume từ 1,00 xuống 0,65 để hạn chế quá mức. Có thể hoàn nguyên bằng wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 1.0. Không giải quyết hiện tượng méo và nhầm đích chỉ bằng cách hạ ngưỡng confidence.")

    r.page("9. Phân tích câu lệnh và nhiều điểm đến")
    r.p("Parser chuẩn hóa chữ thường, dấu câu, khoảng trắng và dấu tiếng Việt để so sánh. Đích chỉ được tra trong từ điển alias hợp lệ; chương trình không tìm tên vùng bằng việc thấy một chữ cái bất kỳ trong câu. Nhờ đó các đoạn như “A B” hoặc câu phủ định không bị biến thành mục tiêu di chuyển.")
    r.table(["Câu lệnh", "Kết quả"],[
        ["Đi đến phòng học", "[A]"],
        ["Đi đến phòng thí nghiệm", "[B]"],
        ["Đi đến hành lang", "[C]"],
        ["Di chuyển từ phòng học đến phòng thí nghiệm", "[A, B]"],
        ["Đi từ phòng A qua phòng C rồi đến phòng B", "[A, C, B]"],
        ["Dừng lại / Hủy lệnh", "[] — yêu cầu hủy"],
        ["Đi từ A đến D", "Từ chối toàn bộ câu, không đi A trước"],
        ["Không đi đến A / Đi đến A B", "Từ chối câu không thuộc mẫu"]])
    r.heading("Kiểm tra toàn bộ câu trước khi chạy")
    r.p("Lệnh được tách theo các từ khóa từ/qua/rồi đến/đến; mọi thành phần cần khớp alias. Nếu có một vùng không tồn tại, toàn bộ request bị loại trước khi gửi action đầu tiên. Hành trình giới hạn tối đa 10 đích. Hai vùng không được trùng alias sau chuẩn hóa, vì bỏ dấu có thể khiến hai tên vốn khác nhau trở nên mơ hồ.")
    r.heading("Ý nghĩa của “từ A đến B”")
    r.p("Trong bài này, A là điểm phải ghé trước, không phải một lời khẳng định vị trí hiện tại. Nếu robot đang ở C và nhận “từ A đến B”, robot vẫn đi tới pose A, chờ Nav2 báo thành công, rồi mới tới B. Robot không tự bỏ A dựa trên tên phòng người dùng nói. Cách này đáp ứng đúng yêu cầu đi qua nguồn khi robot ở một vị trí khác.")
    r.p("Một câu ASR có confidence cao vẫn có thể sai ngữ nghĩa: log từng có “nghiệm đến phòng học” ở mức 0,75. Parser tiếp tục là một lớp kiểm tra độc lập và từ chối câu đó. Confidence của ASR không thay cho kiểm tra ngữ pháp và vùng đích.")

    r.page("10. Điều hướng Nav2 và xử lý trạng thái")
    r.fig("06_states.png","Sơ đồ rút gọn quản lý hành trình theo navigation_node.py.")
    r.p("Khi có câu hợp lệ, node kiểm tra action server navigate_to_pose đã sẵn sàng và node có đang bận không. Nếu chưa có server, trả NOT_READY và không lưu lệnh để tự chạy sau. Nếu đang bận, trả BUSY, giữ hành trình cũ; người dùng cần hủy và chờ kết thúc trước khi gửi một hành trình khác.")
    r.p("Mỗi đích được đóng gói trong PoseStamped, frame map, timestamp theo ROS clock và quaternion từ yaw. ActionClient gửi bất đồng bộ. Chỉ khi goal được chấp nhận mới chờ result; chỉ STATUS_SUCCEEDED cùng error_code=0 mới cho phép chuyển sang đích tiếp theo. Nav2 đảm nhận planner, controller, costmap, recovery và tránh vật cản theo cấu hình hiện có [1].")
    r.table(["Trạng thái", "Cách xử lý"],[
        ["READY","Đã nạp cấu hình; chưa có nghĩa localization/Nav2 đều sẵn sàng"],
        ["ROUTE / NAVIGATING","Đã hiểu chuỗi và đang gửi/thực hiện một đích"],
        ["FEEDBACK / ARRIVED","Khoảng cách còn lại / hoàn thành một chặng"],
        ["SUCCEEDED","Hoàn thành toàn bộ chuỗi"],
        ["REJECTED / FAILED","Dừng chuỗi, không gửi đích còn lại"],
        ["CANCELING / STOPPED","Yêu cầu hủy / action kết thúc sau yêu cầu hủy"]])
    r.p("Timeout dùng time.monotonic và timer steady, để không phụ thuộc việc /clock mô phỏng có chạy hay bị pause. Khi timeout hoặc hủy, xóa deque đích còn lại. Nếu kết quả truyền goal/hủy không chắc chắn, node giữ khóa hành trình, không mở đường cho một goal chồng lên goal cũ chưa biết trạng thái.")

    r.page("11. Dừng khi đang chạy và quan sát hệ thống")
    r.heading("11.1. Hủy bằng giọng nói")
    r.p("Người dùng có thể nói “dừng lại”, “dừng”, “hủy”, “hủy lệnh” ngay khi robot đang thực hiện. Khi câu được ASR chốt đúng, node phát yêu cầu cancel cho goal hiện hành và bỏ các điểm tiếp theo. Terminal 2 lần lượt hiện CANCELING và STOPPED. Nếu yêu cầu hủy đến khi goal còn đang chờ chấp nhận, cờ cancel_requested bảo đảm goal bị hủy ngay sau khi có handle.")
    r.p("Trong log thực tế, câu “dừng c” dù confidence 0,81 vẫn bị parser từ chối vì không phải lệnh dừng hoàn chỉnh. Sau đó “dừng lại” ở mức 0,77 được chấp nhận và tạo STOPPED. Điều này cho thấy cần quan sát trạng thái hủy, không chỉ dựa vào việc đã phát âm một từ gần giống.")
    r.p("Hủy action bằng giọng nói không phải cơ chế dừng khẩn cấp vật lý. Nó có độ trễ thu âm, kết thúc câu, nhận dạng, truyền lệnh và phản ứng controller. Khi không nhận được phản hồi, Ctrl+C ở Terminal 2 gửi hủy trực tiếp; chương trình chờ tối đa ba giây để nhận xác nhận trước khi thoát. Không đồng nhất thời điểm STOPPED của action với phép đo robot đã dừng cơ khí.")
    r.heading("11.2. Terminal và RViz")
    r.table(["Nơi quan sát", "Thông tin cần xem"],[
        ["Terminal 1","Gazebo, undock SUCCEEDED, lifecycle localization/navigation active"],
        ["Terminal 2","ROUTE, NAVIGATING, ARRIVED, SUCCEEDED, CANCELING/STOPPED"],
        ["Terminal 3","Vosk sẵn sàng, PARTIAL, ASR, cảnh báo confidence, AUDIO"],
        ["/voice_nav/transcript","Văn bản và trạng thái đầu vào"],
        ["/voice_nav/status","JSON trạng thái hành trình"],
        ["/voice_nav/markers","MarkerArray nhãn vùng và thứ tự đích trong RViz"]])
    r.p("RViz dùng Fixed Frame map; MarkerArray nên dùng Transient Local để xem nhãn đã publish trước khi mở giao diện. Đường nối các đích chỉ minh họa thứ tự, có thể cắt qua tường. Đường đi tránh vật cản phải xem từ planner Nav2, không sử dụng đường nối marker như quỹ đạo điều khiển.")

    r.page("12. Quy trình cài đặt và tái lập")
    r.p("Các lệnh giả định workspace ~/tb4_slam_ws. Cần cài ROS 2 Jazzy, TurtleBot 4 simulation và các dependency Nav2 của repository trước; khối dưới bổ sung thư viện bài 7. Venv phải dùng --system-site-packages để nhìn thấy rclpy và các thư viện ROS/Python hệ thống.")
    r.code("cd ~/tb4_slam_ws\nsudo apt install python3-venv python3-opencv python3-yaml \\\n  python3-scipy alsa-utils ros-jazzy-nav2-msgs \\\n  ros-jazzy-visualization-msgs\npython3 -m venv --system-site-packages bai_07_voice_navigation/.venv\nbai_07_voice_navigation/.venv/bin/python -m pip install \\\n  -r bai_07_voice_navigation/requirements.txt\nsource /opt/ros/jazzy/setup.bash\ncolcon build --symlink-install --packages-select tb4_assignment")
    r.heading("Model và bản đồ")
    r.p("Model tiếng Việt hiện được dùng lại từ bai_05_dialogue/models/vosk-model-small-vn-0.4. Trên máy khác có thể tải model từ danh sách Vosk [2], giải nén và truyền --model tương ứng. Không cần đưa cả model/venv lên GitHub. Khi tạo lại vùng, chạy segment_map.py; khi dùng map khác, điều chỉnh cả launch Nav2, --regions và initial pose phù hợp.")
    r.code("python3 bai_07_voice_navigation/segment_map.py\npython3 -m unittest discover -s bai_07_voice_navigation/tests -v")
    r.heading("Trình tự vận hành")
    r.p("Khởi động mô phỏng và chờ undock/lifecycle active; sau đó mở node điều hướng; cuối cùng mở micro. Không chạy đồng thời teleop hoặc behavior node cũ đang publish vận tốc. Mỗi terminal dùng cùng RMW_IMPLEMENTATION, ROS domain và workspace đã source. Nếu nghi có node cũ, kiểm tra PID/câu lệnh trước khi dừng để tránh đóng nhầm ứng dụng khác.")
    r.p("Trước khi thử giọng nói điều khiển, có thể chạy --listen-only --audio-level để xem đúng câu và mức tín hiệu mà không làm robot di chuyển. Sau mỗi hành trình chờ SUCCEEDED ở Terminal 2; ARRIVED của một chặng trung gian chưa có nghĩa toàn bộ chuỗi đã hoàn thành.")

    r.page("13. Lệnh khởi chạy đầy đủ cho ba terminal")
    r.heading("Terminal 1 — Gazebo, localization và Nav2")
    r.code("cd ~/tb4_slam_ws\nsource /opt/ros/jazzy/setup.bash\nsource install/setup.bash\nexport RMW_IMPLEMENTATION=rmw_fastrtps_cpp\nros2 launch tb4_assignment navigation.launch.py auto_undock:=true")
    r.p("Launch chạy Nav2 trễ 25 giây; cần chờ thông báo Managed nodes are active và undock thành công. Kiểm tra LiDAR/robot khớp map; dùng 2D Pose Estimate khi AMCL chưa đúng. Không gửi lệnh di chuyển khi robot còn đang undock.")
    r.heading("Terminal 2 — hiểu lệnh và gửi action")
    r.code("cd ~/tb4_slam_ws\nsource /opt/ros/jazzy/setup.bash\nsource install/setup.bash\nexport RMW_IMPLEMENTATION=rmw_fastrtps_cpp\npython3 bai_07_voice_navigation/navigation_node.py \\\n  --goal-timeout 300 --ros-args -p use_sim_time:=true")
    r.heading("Terminal 3 — nhận giọng nói")
    r.code("cd ~/tb4_slam_ws\nsource /opt/ros/jazzy/setup.bash\nsource install/setup.bash\nexport RMW_IMPLEMENTATION=rmw_fastrtps_cpp\nbai_07_voice_navigation/.venv/bin/python \\\n  bai_07_voice_navigation/voice_input.py \\\n  --mic --device pipewire --audio-level --highpass 150")
    r.p("Chờ Vosk sẵn sàng; nói “Đi đến phòng học”, rồi ngừng khoảng 1–2 giây. Sau SUCCEEDED thử “Đi đến phòng thí nghiệm” và “Đi đến hành lang”. Khi kết thúc, dừng Terminal 3 trước, Ctrl+C Terminal 2 để hủy có kiểm soát, rồi mới dừng Terminal 1.")

    r.page("14. Kiểm thử tự động và mức độ chứng minh")
    r.table(["Nhóm", "Số test", "Nội dung chính"],[
        ["Logic bản đồ và parser","14","Tọa độ xoay, unknown, negate, clearance, liên thông, hash, câu đơn/chuỗi/alias"],
        ["ROS action với fake Nav2","6","Tuần tự, vùng sai, failure, rejection, BUSY/cancel, timeout"],
        ["ASR helper và bộ lọc","7","Grammar giữ unknown, minimum confidence, mức âm, byte lẻ, đáp tuyến và chunk state"],
        ["Tổng","27/27 đạt","Log: results/automated_tests.log"]])
    r.p("Các test action dùng ROS_DOMAIN_ID=87 và server NavigateToPose giả lập, để kiểm tra giao tiếp ROS thật mà không tác động robot mô phỏng ở domain vận hành. Server có thể chấp nhận, từ chối, báo lỗi hoặc chờ hủy. Test A → B kiểm tra frame map, tọa độ và thứ tự ARRIVED; B chỉ được gửi sau kết quả thành công của A.")
    r.p("Các test bộ lọc dùng tín hiệu tổng hợp với tần số đã biết; chúng chứng minh đáp ứng và tính liên tục của thuật toán, không phải bài đánh giá giọng nói. Tương tự, test grammar và parser không đo WER. Kết quả 27/27 không đồng nghĩa 100% lệnh nói được nhận đúng.")
    r.heading("Kiểm tra tích hợp có Gazebo thật")
    r.p("Đã chạy Gazebo headless với Nav2 thật, undock SUCCEEDED và gửi câu chữ tới A. Feedback giảm từ khoảng 4,21 m xuống vùng đích, sau đó ARRIVED A/SUCCEEDED khoảng 41 giây. Trong lúc robot đang đi, gửi vùng D bằng node text trả INVALID_COMMAND, không thay hành trình A. Đây là smoke test nối từ parser đến chuyển động, tách khỏi chất lượng ASR.")
    r.heading("Kịch bản cần giữ khi nghiệm thu")
    r.p("Thử ba tên vùng qua micro; thử từ A đến B khi robot ở vùng khác; thử vùng không tồn tại trong câu đơn và chuỗi; thử dừng lúc đang chạy; thử BUSY; thử timeout; kiểm tra lại hash khi đổi map. Với tránh vật cản động, cần dựng một ca riêng trong Gazebo và quan sát costmap/quỹ đạo; chưa dùng log action để kết luận robot đã tránh một vật cản cụ thể.")

    r.page("15. Kết quả phiên điều khiển bằng giọng nói")
    r.fig("08_evidence.png","Tóm lược các dòng log thực tế được dàn lại để dễ đọc; nguồn lưu trong results/voice_session_*.log.")
    r.p("Sau khi bổ sung grammar, lọc tiếng ù, chỉnh mức thu và dùng tên nhiều âm tiết, phiên thực tế ghi nhận “đi đến phòng học” confidence 0,99; “đi đến phòng thí nghiệm” 0,87; “đi đến hành lang” 1,00. Những con số này là confidence do Vosk trả về cho từng câu, không phải phần trăm chính xác đo trên tập kiểm thử.")
    r.table(["Lệnh đầu tiên rõ ràng", "Kết quả theo log", "Thời gian"],[
        ["Đi đến phòng học → A","ARRIVED A / SUCCEEDED","40,16 s"],
        ["Đi đến phòng thí nghiệm → B","ARRIVED B / SUCCEEDED","179,26 s"],
        ["Đi đến hành lang → C","Nhận đích C; người dùng hủy","114,82 s đến STOPPED"],
        ["Dừng lại (trong lượt C)","CANCELING → STOPPED","khoảng 26 ms ở tầng action"]])
    r.p("Thời gian trên tính từ timestamp log ROUTE đến SUCCEEDED/STOPPED bằng đồng hồ ghi log. Nó không phải navigation_time mô phỏng và không bao gồm thời gian người dùng phát âm trước khi ASR chốt câu. Khoảng 26 ms chỉ tính từ CANCELING đến STOPPED; không đo độ trễ toàn tuyến bằng giọng nói hoặc thời gian dừng cơ khí.")
    r.p("Log cũng còn một số câu sai và câu bị loại. Vì không lưu tập âm thanh có nhãn cũng như số lần nói thực tế, báo cáo không tính WER, tỷ lệ nhận đúng hay tỷ lệ thất bại ASR. Người dùng xác nhận vận hành ổn định là nhận xét nghiệm thu định tính, được bổ trợ bằng các chuỗi thành công có timestamp.")

    r.page("16. Phân tích tám lượt điều hướng thực tế")
    r.fig("07_missions.png","Thời gian các lượt trong phiên giọng nói; màu cam là hủy chủ động, không được coi là lỗi điều hướng.")
    r.table(["Lượt", "Đích", "Trạng thái cuối", "Thời gian (s)"],[
        [i,m["route"][0],"Thành công" if m["state"]=="SUCCEEDED" else "Người dùng hủy",f"{m['duration']:.2f}"] for i,m in enumerate(missions,1)])
    r.p("Tám lượt được đối chiếu từ file navigation thực tế: bốn lượt hoàn thành (một lượt A, ba lượt B) và bốn lượt kết thúc sau lệnh hủy. Không lấy 4/8 làm tỷ lệ thành công, vì các lượt hủy là thao tác chủ động của người dùng, không phải lỗi planner. Chưa có bằng chứng ARRIVED C trong tập log đã trích.")
    r.p("Thời gian đến B thay đổi giữa các lượt do vị trí xuất phát và diễn biến hành trình khác nhau. Không dùng các thời gian này để so sánh hiệu năng thuật toán khi chưa chuẩn hóa vị trí ban đầu, điều kiện mô phỏng và tải hệ thống. Log cho thấy cơ chế gửi goal, nhận feedback, nhận kết quả và hủy hoạt động xuyên suốt chuỗi ASR → parser → Nav2.")

    r.page("17. Các lỗi đã gặp: môi trường và tích hợp ROS")
    r.table(["Sự cố thực tế", "Nguyên nhân / chẩn đoán", "Cách khắc phục"],[
        ["Tạo venv lỗi ensurepip; không có pip","Thiếu thành phần venv/pip của Python hệ thống","Máy khác cài python3-venv. Trong phiên triển khai đã bootstrap pip vào venv cục bộ."],
        ["Venv import rclpy báo thiếu yaml","include-system-site-packages=false sau lần tạo không hoàn chỉnh","Tạo lại với --without-pip --system-site-packages, giữ pip đã có; kiểm tra import rclpy/cv2/yaml."],
        ["AttributeError: handle cannot be modified after node creation","Dùng self.handle làm biến action, trùng property Node.handle của rclpy","Đổi thành self.goal_handle; chạy lại test action thật."],
        ["Lời gọi connectedComponentsWithStats chưa chỉ rõ connectivity","Đối số 4 đặt theo vị trí không biểu đạt đúng tham số connectivity","Sửa connectivity=4; thêm test thành phần chéo để xác minh bốn hướng."],
        ["Lo ngại tiến trình/node cũ còn chạy","Có thể còn publisher hoặc launch chiếm tài nguyên sau các lượt thử","Kiểm tra PID và câu lệnh; gửi SIGINT cho node/launch cụ thể; kiểm tra lại trước khi mở ba terminal."],
        ["CLI báo subscriber=0 nhưng process node vẫn chạy","Ảnh chụp graph CLI ban đầu chưa phản ánh kết nối đã được xác nhận sau đó","Tạo node chẩn đoán trực tiếp, chờ discovery; thấy subscriber và gửi vùng D nhận INVALID_COMMAND. Không kết luận mất DDS chỉ từ một lệnh CLI."]])
    r.p("Các lỗi này cho thấy cần phân biệt lỗi môi trường Python, lỗi API ROS và lỗi giao tiếp. Ví dụ rclpy import được chưa chứng minh model Vosk nạp được; process còn chạy chưa chứng minh nó đã nhận topic. Chỉ sửa đúng tầng gặp lỗi, rồi kiểm tra lại bằng một request không gây chuyển động như vùng D.")
    r.p("Trong quá trình phát triển cũng có một lần apply_patch không khớp dòng .gitignore; bản sửa được áp dụng lại đúng context. Đây là sự cố thao tác phát triển, không phải lỗi thời gian chạy của robot và không ảnh hưởng đến bản đồ/đích cuối.")

    r.page("18. Các lỗi đã gặp: nhận dạng giọng nói")
    r.table(["Hiện tượng", "Bằng chứng thực tế", "Biện pháp đã áp dụng"],[
        ["ASR trả từ không liên quan","Các đoạn “sửa chữa”, “nhìn liễu cuộc đời”; một số confidence vẫn cao","Dùng grammar điều hướng theo vùng; parser kiểm tra câu độc lập; giữ [unk]."],
        ["Cảnh báo câu rỗng liên tục","Nhiều dòng confidence 0,00 khi im lặng","Bỏ cảnh báo cho text rỗng; chỉ ghi cảnh báo khi có câu cần nói lại."],
        ["Terminal 2 không có phản hồi khi nói","Log Terminal 3 loại câu thấp ngưỡng hoặc chỉ có PARTIAL","Kiểm tra ASR final và topic; gửi D xác minh node 2; thêm --listen-only và audio level."],
        ["Tiếng ù dù môi trường cảm nhận đã yên","92,2% năng lượng dưới 150 Hz; đỉnh 35,3 Hz","High-pass 150 Hz, bậc 4; giữ trạng thái bộ lọc qua chunk."],
        ["Nói to khiến tín hiệu bão hòa","Một số log sau lọc clipping đến 9,8–10,8%","Giảm nguồn thu 1,00 → 0,65; không cố chữa bằng giảm confidence."],
        ["Nhầm âm cuối A/bê/dê/xê","Partial A nhưng final thành dê/bê; confidence 0,30–0,57","Thêm tên nhiều âm tiết và một/hai/ba; không tự đổi D sang A."],
        ["Từ cê không có trong model","Vosk cảnh báo Ignoring word missing in vocabulary","Tra vocabulary trước; bỏ cả phrase chứa từ ngoài model, giữ các alias còn hỗ trợ."],
        ["Đổi alias nhưng node vẫn dùng dữ liệu cũ","Hai tiến trình nạp từ điển/grammar lúc khởi động","Khởi động lại cả Terminal 2 và 3 sau khi sửa YAML."]])
    r.p("Nguyên nhân không chỉ nằm ở tiếng ồn môi trường. Trường hợp này kết hợp chất lượng tín hiệu thu, mức gain, khả năng model nhỏ phân biệt chữ cái và ngưỡng minimum-word-confidence. Việc làm yên phòng là cần thiết nhưng không đủ để chứng minh tín hiệu PCM không còn ù hoặc clipping.")

    r.page("19. Quy trình chẩn đoán khi tái xuất hiện lỗi")
    r.heading("Bước 1 — Xác định tầng bị ngắt")
    r.p("Kiểm tra Terminal 3 có Vosk sẵn sàng, AUDIO, PARTIAL và ASR final hay không. Nếu chỉ có PARTIAL hoặc cảnh báo confidence thấp, chưa có command gửi sang Terminal 2. Nếu có ASR nhưng Terminal 2 không trả trạng thái, kiểm tra topic/subscriber và môi trường ROS. Nếu Terminal 2 có NAVIGATING nhưng robot không tiến, xem localization, action result, costmap và controller ở Terminal 1.")
    r.code("ros2 topic info /voice_nav/command -v\nros2 topic echo /voice_nav/status\nros2 topic echo /voice_nav/transcript\nros2 action info /navigate_to_pose\nwpctl status\nwpctl get-volume @DEFAULT_AUDIO_SOURCE@\narecord -L")
    r.heading("Bước 2 — Tách micro khỏi chuyển động")
    r.code("bai_07_voice_navigation/.venv/bin/python \\\n  bai_07_voice_navigation/voice_input.py \\\n  --mic --device pipewire --listen-only --audio-level --highpass 150")
    r.p("Nói một câu nhiều âm tiết rồi im lặng; chỉ khi thấy câu cuối đúng mới ghép lại điều khiển robot. So sánh --highpass 0 nếu cần. Các tín hiệu tổng hợp hoặc log text không thể thay cho việc nghe/đối chiếu một tập âm thanh nói thực tế có nội dung chuẩn.")
    r.heading("Bước 3 — Thử riêng đường truyền lệnh")
    r.code("ros2 topic pub --once -w 1 /voice_nav/command \\\n  std_msgs/msg/String '{data: \"Đi đến khu vực D\"}'")
    r.p("Lệnh vùng D không tạo chuyển động nhưng kiểm tra được subscriber, callback và parser. Kết quả mong đợi INVALID_COMMAND. Khi xác nhận truyền thông đúng, mới thử một đích hợp lệ. Không mở thêm nhiều navigation node cùng tên để chẩn đoán vì sẽ làm khó phân biệt trạng thái.")
    r.heading("Bước 4 — Xác nhận thay đổi đã có hiệu lực")
    r.p("Xem command line của tiến trình để biết đã có --highpass 150 và đúng --regions/--model. Sau sửa mã hoặc alias, tiến trình Python cũ vẫn giữ dữ liệu trong bộ nhớ; cần Ctrl+C và chạy lại node liên quan. Không cần khởi động lại Gazebo mỗi khi chỉ đổi tên vùng hoặc ASR.")

    r.page("20. Đánh giá, hạn chế và hướng phát triển")
    r.heading("Kết quả đạt được")
    r.p("Đã tích hợp bản đồ ba vùng có đích hợp lệ, semantic aliases, nhận giọng nói tiếng Việt offline, phân tích hành trình nhiều điểm và điều hướng Nav2. Có xử lý vùng không tồn tại, BUSY, failure/rejection, timeout và hủy trong khi đang thực hiện. Người dùng xác nhận hệ thống hoạt động sau các điều chỉnh. Dữ liệu ghi log chứng minh nhận ba tên vùng, đến A/B và hủy các hành trình đang chạy.")
    r.heading("Hạn chế cần ghi đúng")
    r.p("Phân vùng hiện là chia không gian chức năng trên thành phần sàn chính, chưa tự hiểu ranh giới/phân loại phòng. Seed mặc định có thể tạo vùng lệch diện tích. Minimum confidence có thể làm phải nói lại nhiều lần. Lệnh giọng nói ngắn vẫn có thể nhận sai; grammar không đảm bảo câu ngoài phạm vi luôn được nhận là [unk]. Hủy giọng nói không thay thế cơ chế an toàn vật lý.")
    r.p("Chưa có thống kê WER/command accuracy dựa trên bộ âm thanh gán nhãn, chưa đo dừng cơ khí và chưa có thí nghiệm vật cản động được chuẩn hóa. Trong log được trích, C đã nhận yêu cầu nhưng bị hủy, chưa có ARRIVED C. Chưa có URL GitHub Public hay video demo được đính kèm trong dữ liệu báo cáo. Không dùng các mục còn thiếu làm kết quả đã đạt.")
    r.heading("Hướng cải tiến")
    r.p("Có thể bổ sung segmentation theo cửa/phòng hoặc watershed có kiểm tra topology; giao diện chỉnh tên và đích thủ công; backend ASR khác như Whisper để đối chiếu; thu tập câu nói nhiều người và tính confusion matrix cho từng vùng. Với nhiều điểm đến, nên hiển thị chuỗi dự kiến rõ ràng và phân biệt đường nối mục tiêu với Path tránh vật cản do Nav2 tạo.")
    r.p("Để đánh giá định lượng, cố định pose ban đầu và điều kiện mô phỏng, mỗi câu thử ít nhất năm lần; ghi nội dung chuẩn, bản nhận dạng, confidence, ID được chọn, trạng thái action và thời gian. Thử hủy ở nhiều giai đoạn; tách thời gian ASR chốt câu khỏi thời gian action xác nhận hủy. Mọi trường hợp chưa rõ đích cần từ chối hoặc hỏi lại thay vì đoán sang một vùng hợp lệ.")

    r.page("21. Tài liệu, sản phẩm và phụ lục minh chứng")
    r.table(["Sản phẩm", "Đường dẫn trong thư mục bài 7"],[
        ["Mã xử lý bản đồ / parser","map_tools.py; segment_map.py; commands.py"],
        ["Mã thu âm / ASR / ROS","speech.py; voice_input.py; navigation_node.py"],
        ["Bản đồ và nhãn","maps/original.*; labels.png; segmented_map.png; regions.yaml"],
        ["Kiểm thử và hướng dẫn","tests/; TEST_CASES.md; README.md; VALIDATION.md"],
        ["Log tự động / Gazebo text","results/automated_tests.log; gazebo_navigation.log"],
        ["Log phiên giọng nói","results/voice_session_asr.log; voice_session_navigation.log"],
        ["Bảng phiên được trích","results/voice_session_summary.json"],
        ["Hình và mã tạo báo cáo","report_assets/; generate_detailed_report.py"],
        ["Báo cáo ngắn / báo cáo chi tiết","report.pdf; Bao_cao_chi_tiet_Bai_07.docx/.doc/.pdf"]])
    r.heading("Nguồn tham khảo")
    for text in [
        "[1] Nav2, NavigateToPose Action — Jazzy: https://api.nav2.org/actions/jazzy/navigatetopose.html. Tham khảo cấu trúc goal, feedback, result.",
        "[2] Alpha Cephei, Vosk Models: https://alphacephei.com/vosk/models. Model sử dụng: vosk-model-small-vn-0.4.",
        "[3] Vosk API, mã nguồn và ví dụ: https://github.com/alphacep/vosk-api. Tham khảo grammar, SetWords và KaldiRecognizer.",
        "[4] SciPy, scipy.signal.sosfilt: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfilt.html. Tham khảo bộ lọc SOS và trạng thái zi/zf.",
        "[5] Dữ liệu triển khai tại workspace ~/tb4_slam_ws: mã nguồn, map YAML/PGM, log ROS và log kiểm thử. Truy cập/đối chiếu ngày 06/11/2026."]:
        r.p(text)
    r.heading("Ghi chú về hình ảnh và tính tái lập")
    r.p("Tất cả hình được tạo từ bản đồ thật, cấu hình bộ lọc, mã nguồn hoặc timestamp log của bài thực hành. Sơ đồ kiến trúc/trạng thái và hình trích log là hình giải thích được dàn lại, không giả làm ảnh chụp Gazebo/RViz. Không dùng ảnh tạo sinh để minh họa thành công của robot. File Word để trống thông tin sinh viên, lớp và giảng viên vì chưa được cung cấp.")
    # Each chapter is deliberately one page in the validated A4 layout.
    # Insert the contents after the cover, retaining the chapter page breaks.
    chapters=[p.text for p in r.doc.paragraphs if p.style.name=="Heading 1" and re.match(r"^\d+\.",p.text)]
    old_elements=set(r.doc._element.body)
    r.doc.add_page_break()
    r.heading("Mục lục",1)
    for page,title in enumerate(chapters,3):
        p=r.doc.add_paragraph()
        p.paragraph_format.space_after=Pt(4)
        p.paragraph_format.tab_stops.add_tab_stop(Cm(16.6),WD_TAB_ALIGNMENT.RIGHT,WD_TAB_LEADER.DOTS)
        run=p.add_run(title+"\t"+str(page));run.font.size=Pt(11)
    for element in list(r.doc._element.body):
        if element not in old_elements:
            contents_anchor._p.addprevious(element)
    r.doc.save(OUTPUT)
    print(OUTPUT)
    print(f"Illustrations: {r.figure_index}; missions: {len(missions)}")


if __name__ == "__main__":
    main()
