from flask import (
    Flask,
    render_template,
    request,
    flash,
    url_for,
    redirect,
    session,
    send_file,
)
from bokeh.embed import components
from bokeh.plotting import figure
from bokeh.resources import INLINE
from werkzeug.utils import secure_filename
import tempfile
import traceback
from datetime import timedelta

import os, sys
import stlearn
import scanpy
import numpy
import numpy as np

import asyncio
from bokeh.server.server import BaseServer
from bokeh.server.tornado import BokehTornado
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from bokeh.application import Application
from bokeh.application.handlers import FunctionHandler
from bokeh.server.server import Server
from bokeh.embed import server_document

from bokeh.layouts import column, row

# Functions related to processing the forms.
from source.forms import views  # for changing data in response to input

# Global variables.

global adata  # Storing the data

# adata = None
global step_log  # Keeps track of what step we're up to (performed preprocessing?)
step_log = {
    "uploaded": [True, "Upload file"],
    "preprocessed": [True, "Preprocessing"],
    "clustering": [True, "Clustering"],
    "psts": [True, "Spatial trajectory"],
    "dea": [True, "DEA"],
    "lr": [True, "Ligand-receptor analysis"],
    "cci": [True, "CCI"],
    # _params suffix important for templates/progress.html
    "preprocessed_params": {},
    "cci_params": {},
    "cluster_params": {},
    "psts_params": {},
    "dea_params": {},
    "lr_params": {},
}

# print(stlearn, file=sys.stdout)

server = Flask(__name__)
server.secret_key = b'_5#y2L"F4Q8z\n\xec]/'
server.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=20)

UPLOAD_FOLDER = "uploads/"
TEMPLATES_AUTO_RELOAD = True
server.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
server.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
server.config["TEMPLATES_AUTO_RELOAD"] = TEMPLATES_AUTO_RELOAD
server.config["SESSION_PERMANENT"] = False


@server.route("/", methods=["GET"])
def index():
    return render_template("index.html", step_log=step_log)


@server.route("/upload")
def upload():
    return render_template("upload.html", step_log=step_log, flash_bool=True)


@server.route("/preprocessing", methods=["GET", "POST"])
def preprocessing():
    global adata, step_log
    updated_page = views.run_preprocessing(request, adata, step_log)
    return updated_page


@server.route("/clustering", methods=["GET", "POST"])
def clustering():
    global adata, step_log
    updated_page = views.run_clustering(request, adata, step_log)
    return updated_page


@server.route("/lr", methods=["GET", "POST"])
def lr():
    global adata, step_log
    updated_page = views.run_lr(request, adata, step_log)
    return updated_page


@server.route("/cci", methods=["GET", "POST"])
def cci():
    global adata, step_log
    updated_page = views.run_cci(request, adata, step_log)
    return updated_page


@server.route("/psts", methods=["GET", "POST"])
def psts():
    global adata, step_log

    if "clusters" not in adata.obs.columns:
        return redirect(url_for("choose_cluster"))
    else:
        updated_page = views.run_psts(request, adata, step_log)
        return updated_page


@server.route("/dea", methods=["GET", "POST"])
def dea():
    global adata, step_log
    updated_page = views.run_dea(request, adata, step_log)
    return updated_page


allow_files = [
    "filtered_feature_bc_matrix.h5",
    "tissue_hires_image.png",
    "tissue_lowres_image.png",
    "tissue_positions_list.csv",
    "scalefactors_json.json",
]


@server.route("/folder_uploader", methods=["GET", "POST"])
def folder_uploader():
    if request.method == "POST":
        # Clean uploads folder before upload a new data
        import shutil

        shutil.rmtree(server.config["UPLOAD_FOLDER"])
        os.makedirs(server.config["UPLOAD_FOLDER"])
        open(server.config["UPLOAD_FOLDER"] + "/.gitkeep", "a").close()
        # os.mknod()

        # Get list of files from selected folder
        files = request.files.getlist("file")

        os.mkdir(os.path.join(server.config["UPLOAD_FOLDER"], "spatial"))

        # allow_upload_files = list(map(lambda x: x ),allow_files)

        uploaded = []
        i = 0
        for file in files:

            filename = secure_filename(file.filename)

            print(filename)

            if allow_files[0] in filename:
                file.save(os.path.join(server.config["UPLOAD_FOLDER"], filename))
                os.rename(
                    os.path.join(server.config["UPLOAD_FOLDER"], filename),
                    os.path.join(server.config["UPLOAD_FOLDER"], allow_files[0]),
                )
                uploaded.append(allow_files[0])

            for allow_file in allow_files[1:]:
                if allow_file in filename:

                    file.save(
                        os.path.join(
                            server.config["UPLOAD_FOLDER"] + "/spatial", filename
                        )
                    )
                    os.rename(
                        os.path.join(
                            server.config["UPLOAD_FOLDER"] + "/spatial", filename
                        ),
                        os.path.join(
                            server.config["UPLOAD_FOLDER"] + "/spatial", allow_file
                        ),
                    )

                    uploaded.append(allow_file)
            i += 1
            if len(uploaded) == 5:
                flash("File uploaded successfully")
                global adata, step_log
                # step_log = {
                #     "uploaded": [False, "Upload file"],
                #     "preprocessed": [False, "Preprocessing"],
                #     "clustering": [False, "Clustering"],
                #     "psts": [False, "Spatial trajectory"],
                #     "cci_rank": [False, "Cell-cell interaction"],
                #     "dea": [False, "Differential expression analysis"],
                #     # _params suffix important for templates/progress.html
                #     "preprocessed_params": {},
                #     "cci_params": {},
                #     "cluster_params": {},
                #     "psts_params": {},
                #     "dea_params": {},
                # }
                adata = stlearn.Read10X(server.config["UPLOAD_FOLDER"])
                adata.var_names_make_unique()  # removing duplicates
                # ensuring compatible format for CCI, since need _ to pair LRs #
                adata.var_names = numpy.array(
                    [var_name.replace("_", "-") for var_name in adata.var_names]
                )

                step_log["uploaded"][0] = True

                return redirect(url_for("upload"))

        if len(uploaded) != 5:
            missing_files = []
            for file in allow_files:
                if file not in uploaded:
                    missing_files.append(file)
            flash("Upload ERROR: Missing " + ", ".join(missing_files))
            return redirect(url_for("upload"))


@server.route("/file_uploader", methods=["GET", "POST"])
def file_uploader():
    if request.method == "POST":

        global adata, step_log

        # Clean uploads folder before upload a new data
        import shutil

        shutil.rmtree(server.config["UPLOAD_FOLDER"])
        os.makedirs(server.config["UPLOAD_FOLDER"])
        open(server.config["UPLOAD_FOLDER"] + "/.gitkeep", "a").close()
        # os.mknod()
        f = request.files["file"]
        filename = secure_filename(f.filename)
        f.save(os.path.join(server.config["UPLOAD_FOLDER"], filename))
        try:
            adata = scanpy.read_h5ad(server.config["UPLOAD_FOLDER"] + "/" + f.filename)
        except:
            flash("Upload ERROR: Please choose the right AnnData file ")

        ### Updating log file with current anndata state ###
        step_log["uploaded"][0] = True

        if "n_cells" in adata.var.columns:
            step_log["preprocessed"][0] = True

        for col in adata.obs.columns:
            if adata.obs[col].dtype.name == "category":
                if col != "sub_cluster_labels":
                    step_log["clustering"][0] = True

        if "global_graph" in adata.uns:
            step_log["psts"][0] = True

        step_log["lr"][0] = "lr_summary" in adata.uns
        step_log["cci"][0] = np.any(["lr_cci_" in key for key in adata.uns])

        return redirect(url_for("upload"))


@server.route("/choose_cluster", methods=["GET", "POST"])
def choose_cluster():
    menu = []

    for col in adata.obs.columns:
        if adata.obs[col].dtype.name == "category":
            if col != "sub_cluster_labels":
                menu.append(col)

    return render_template(
        "choose_cluster.html",
        template="Flask",
        relative_urls=False,
        step_log=step_log,
        menu=menu,
    )


@server.route("/convert_clusters", methods=["GET", "POST"])
def convert_clusters():
    if request.method == "POST":
        adata.obs["clusters"] = adata.obs[request.form["convert_clusters"]]
        scanpy.tl.paga(adata, groups="clusters")
        stlearn.pl.cluster_plot(adata, use_label="clusters")

        return redirect(url_for("psts"))


@server.route("/gene_plot")
def gene_plot():
    script = server_document(
        "http://%s:5006/bokeh_gene_plot" % request.host.split(":")[0]
    )
    return render_template(
        "gene_plot.html",
        script=script,
        template="Flask",
        relative_urls=False,
        step_log=step_log,
    )


@server.route("/cluster_plot")
def cluster_plot():
    script = server_document(
        "http://%s:5006/bokeh_cluster_plot" % request.host.split(":")[0]
    )
    return render_template(
        "cluster_plot.html",
        script=script,
        template="Flask",
        relative_urls=False,
        step_log=step_log,
    )


@server.route("/lr_plot")
def lr_plot():
    script = server_document(
        "http://%s:5006/bokeh_lr_plot" % request.host.split(":")[0]
    )
    return render_template(
        "lr_plot.html",
        script=script,
        template="Flask",
        relative_urls=False,
        step_log=step_log,
    )


@server.route("/spatial_cci_plot")
def spatial_cci_plot():
    script = server_document(
        "http://%s:5006/bokeh_spatial_cci_plot" % request.host.split(":")[0]
    )
    return render_template(
        "spatial_cci_plot.html",
        script=script,
        template="Flask",
        relative_urls=False,
        step_log=step_log,
    )


@server.route("/annotate_plot")
def annotate_plot():
    script = server_document(
        "http://%s:5006/bokeh_annotate_plot" % request.host.split(":")[0]
    )
    return render_template(
        "annotate_plot.html",
        script=script,
        template="Flask",
        relative_urls=False,
        step_log=step_log,
    )


@server.route("/save_adata", methods=["POST"])
def save_adata():
    if request.method == "POST":
        fd, path = tempfile.mkstemp()
        from datetime import datetime

        now = datetime.now()
        date_time = now.strftime("%m-%d-%Y_%H-%M-%S")

        adata.write_h5ad(path)
        return send_file(
            path, as_attachment=True, attachment_filename="adata_" + date_time + ".h5ad"
        )


adata = scanpy.read_h5ad("data/data_bcba.h5ad")
# import scanpy as sc

# adata = st.Read10X("/home/d.pham/10X/TBI_C1/")
# adata.raw = adata
# sc.pp.filter_genes(adata,min_cells=3)
# sc.pp.normalize_total(adata)
# sc.pp.log1p(adata)
# sc.pp.highly_variable_genes(adata, min_mean=0.0125, max_mean=3, min_disp=0.5)
# adata = adata[:, adata.var.highly_variable]

# sc.pp.scale(adata)g

# adata.uns["lr"] = ['Gfap_Ctss']
# st.tl.cci_rank.lr(adata=adata)
# st.tl.cci_rank.permutation(adata,n_pairs=1)

# sc.pp.pca(adata)
# sc.pp.neighbors(adata)
# sc.tl.leiden(adata,resolution=0.6)
# adata.uns["iroot"] = 3733
# st.spatial.trajectory.pseudotime(adata,eps=100,use_rep="X_pca",use_sme=False,use_label="leiden")
# st.spatial.trajectory.pseudotimespace_global(adata,use_label="leiden",list_cluster=[6,7])
# st.pl.cluster_plot(adata,use_label="leiden",show_plot=False)


def modify_doc_gene_plot(doc):
    from stlearn.plotting.classes_bokeh import BokehGenePlot

    gp_object = BokehGenePlot(adata)
    doc.add_root(row(gp_object.layout, width=800))

    gp_object.data_alpha.on_change("value", gp_object.update_data)
    gp_object.tissue_alpha.on_change("value", gp_object.update_data)
    gp_object.spot_size.on_change("value", gp_object.update_data)
    gp_object.gene_select.on_change("value", gp_object.update_data)
    gp_object.cmap_select.on_change("value", gp_object.update_data)

    if len(gp_object.menu) != 0:
        gp_object.use_label.on_change("value", gp_object.update_data)
    gp_object.output_backend.on_change("value", gp_object.update_data)


def modify_doc_cluster_plot(doc):
    from stlearn.plotting.classes_bokeh import BokehClusterPlot

    gp_object = BokehClusterPlot(adata)
    doc.add_root(row(gp_object.layout, width=800))

    gp_object.use_label.on_change("value", gp_object.update_list)
    gp_object.use_label.on_change("value", gp_object.update_data)
    gp_object.data_alpha.on_change("value", gp_object.update_data)
    gp_object.tissue_alpha.on_change("value", gp_object.update_data)
    gp_object.spot_size.on_change("value", gp_object.update_data)
    gp_object.list_cluster.on_change("active", gp_object.update_data)
    gp_object.checkbox_group.on_change("active", gp_object.update_data)
    gp_object.output_backend.on_change("value", gp_object.update_data)
    if "rank_genes_groups" in adata.uns:
        gp_object.n_top_genes.on_change("value", gp_object.update_data)
        gp_object.cmap_select.on_change("value", gp_object.update_data)
        gp_object.plot_select.on_change("value", gp_object.update_data)
        gp_object.min_logfoldchange.on_change("value", gp_object.update_data)


def modify_doc_spatial_cci_plot(doc):
    from stlearn.plotting.classes_bokeh import BokehSpatialCciPlot

    gp_object = BokehSpatialCciPlot(adata)
    doc.add_root(row(gp_object.layout, width=800))

    gp_object.annot_select.on_change("value", gp_object.update_list)
    gp_object.annot_select.on_change("value", gp_object.update_data)
    gp_object.lr_select.on_change("value", gp_object.update_data)
    gp_object.data_alpha.on_change("value", gp_object.update_data)
    gp_object.tissue_alpha.on_change("value", gp_object.update_data)
    gp_object.spot_size.on_change("value", gp_object.update_data)
    gp_object.list_cluster.on_change("active", gp_object.update_data)
    gp_object.output_backend.on_change("value", gp_object.update_data)


def modify_doc_lr_plot(doc):
    from stlearn.plotting.classes_bokeh import BokehLRPlot

    gp_object = BokehLRPlot(adata)
    doc.add_root(row(gp_object.layout, width=800))

    gp_object.data_alpha.on_change("value", gp_object.update_data)
    gp_object.tissue_alpha.on_change("value", gp_object.update_data)
    gp_object.spot_size.on_change("value", gp_object.update_data)
    # gp_object.het_select.on_change("value", gp_object.update_data)
    gp_object.lr_select.on_change("value", gp_object.update_data)
    gp_object.output_backend.on_change("value", gp_object.update_data)


def modify_doc_annotate_plot(doc):
    from stlearn.plotting.classes_bokeh import Annotate

    gp_object = Annotate(adata)
    doc.add_root(row(gp_object.layout, width=800))
    gp_object.data_alpha.on_change("value", gp_object.update_data)
    gp_object.tissue_alpha.on_change("value", gp_object.update_data)
    gp_object.spot_size.on_change("value", gp_object.update_data)


# App for gene_plot
bkapp = Application(FunctionHandler(modify_doc_gene_plot))

# App for cluster_plot
bkapp2 = Application(FunctionHandler(modify_doc_cluster_plot))

# App for lr_plot
bkapp3 = Application(FunctionHandler(modify_doc_lr_plot))

# App for cci_spatial_plot
bkapp3_1 = Application(FunctionHandler(modify_doc_spatial_cci_plot))

# App for annotate_plot
bkapp4 = Application(FunctionHandler(modify_doc_annotate_plot))


def bk_worker():
    asyncio.set_event_loop(asyncio.new_event_loop())

    server = Server(
        {
            "/bokeh_gene_plot": bkapp,
            "/bokeh_cluster_plot": bkapp2,
            # "/bokeh_cci_plot": bkapp3,
            "/bokeh_lr_plot": bkapp3,
            "/bokeh_spatial_cci_plot": bkapp3_1,
            "/bokeh_annotate_plot": bkapp4,
        },
        io_loop=IOLoop(),
        allow_websocket_origin=[
            "127.0.0.1:8000",
            "localhost:8000",
            "0.0.0.0:8000",
            "*",
        ],
    )
    server.start()
    server.io_loop.start()


from threading import Thread

Thread(target=bk_worker).start()

# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=5005, debug=True, use_reloader=True)
