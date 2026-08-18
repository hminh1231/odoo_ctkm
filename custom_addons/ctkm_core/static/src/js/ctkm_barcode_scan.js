/** @odoo-module **/

import { loadJS } from "@web/core/assets";
import { scanBarcode } from "@web/core/barcode/barcode_dialog";
import { isBarcodeScannerSupported } from "@web/core/barcode/barcode_video_scanner";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Component, onMounted, useRef, useState } from "@odoo/owl";

let zxingPromise = null;

function ensureZXing() {
    if (window.ZXing) {
        return Promise.resolve(window.ZXing);
    }
    if (!zxingPromise) {
        zxingPromise = loadJS("/web/static/lib/zxing-library/zxing-library.js").then(
            () => window.ZXing
        );
    }
    return zxingPromise;
}

function clampCanvas(canvas, maxSide) {
    const longest = Math.max(canvas.width, canvas.height);
    if (!longest || longest <= maxSide) {
        return canvas;
    }
    const scale = maxSide / longest;
    const out = document.createElement("canvas");
    out.width = Math.max(1, Math.floor(canvas.width * scale));
    out.height = Math.max(1, Math.floor(canvas.height * scale));
    const ctx = out.getContext("2d");
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(canvas, 0, 0, out.width, out.height);
    return out;
}

function imageToCanvas(image) {
    const canvas = document.createElement("canvas");
    canvas.width = image.naturalWidth || image.width;
    canvas.height = image.naturalHeight || image.height;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(image, 0, 0);
    return clampCanvas(canvas, 1600);
}

function decodeCanvasWithZXing(ZXing, canvas) {
    const hints = new Map([
        [
            ZXing.DecodeHintType.POSSIBLE_FORMATS,
            [
                ZXing.BarcodeFormat.EAN_13,
                ZXing.BarcodeFormat.EAN_8,
                ZXing.BarcodeFormat.CODE_128,
                ZXing.BarcodeFormat.CODE_39,
                ZXing.BarcodeFormat.UPC_A,
                ZXing.BarcodeFormat.UPC_E,
                ZXing.BarcodeFormat.ITF,
            ],
        ],
        [ZXing.DecodeHintType.TRY_HARDER, true],
    ]);
    const reader = new ZXing.MultiFormatReader();
    reader.setHints(hints);
    const source = new ZXing.HTMLCanvasElementLuminanceSource(canvas);
    const bitmap = new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(source));
    try {
        return reader.decodeWithState(bitmap).getText();
    } catch (err) {
        if (err.name === "NotFoundException") {
            return null;
        }
        throw err;
    }
}

function loadImageFromFile(file) {
    return new Promise((resolve, reject) => {
        const url = URL.createObjectURL(file);
        const image = new Image();
        image.onload = () => {
            URL.revokeObjectURL(url);
            resolve(image);
        };
        image.onerror = () => {
            URL.revokeObjectURL(url);
            reject(new Error(_t("Không đọc được ảnh tem.")));
        };
        image.src = url;
    });
}

export class CtkmBarcodeScan extends Component {
    static template = "ctkm_core.BarcodeScan";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.inputRef = useRef("barcodeInput");
        this.fileRef = useRef("fileInput");
        this.cameraSupported = isBarcodeScannerSupported();
        this.state = useState({
            query: "",
            loading: false,
            decoding: false,
            scanned: "",
            found: false,
            matches: [],
            searched: false,
        });
        onMounted(() => this.inputRef.el?.focus());
    }

    formatPrice(value) {
        return new Intl.NumberFormat("vi-VN").format(Math.round(value || 0));
    }

    formatDateTime(value) {
        if (!value) {
            return "";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return new Intl.DateTimeFormat("vi-VN", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        }).format(date);
    }

    onInput(ev) {
        this.state.query = ev.target.value;
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.submitQuery();
        }
    }

    async submitQuery() {
        const code = (this.state.query || "").trim();
        if (!code) {
            this.notification.add(_t("Nhập hoặc quét mã vạch / mã hàng."), { type: "warning" });
            return;
        }
        await this.lookup(code);
    }

    async openCamera() {
        let barcode = null;
        let error = null;
        try {
            barcode = await scanBarcode(this.env, "environment");
        } catch (err) {
            error = err.message;
        }
        if (barcode) {
            this.state.query = barcode;
            await this.lookup(barcode);
            if ("vibrate" in window.navigator) {
                window.navigator.vibrate(80);
            }
            return;
        }
        this.notification.add(error || _t("Không đọc được mã vạch. Thử lại hoặc chụp gần tem hơn."), {
            type: "warning",
        });
    }

    openFilePicker() {
        this.fileRef.el?.click();
    }

    async onFileSelected(ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        this.state.decoding = true;
        try {
            const barcode = await this.decodeFromFile(file);
            if (!barcode) {
                this.notification.add(
                    _t("Không thấy mã vạch trên ảnh. Chụp thẳng, đủ sáng, gần phần vạch kẻ."),
                    { type: "warning" }
                );
                return;
            }
            this.state.query = barcode;
            await this.lookup(barcode);
        } catch (err) {
            this.notification.add(err.message || _t("Không đọc được ảnh tem."), { type: "danger" });
        } finally {
            this.state.decoding = false;
        }
    }

    async decodeFromFile(file) {
        const image = await loadImageFromFile(file);
        const canvas = imageToCanvas(image);
        if (typeof window.BarcodeDetector !== "undefined") {
            try {
                const detector = new window.BarcodeDetector({
                    formats: ["ean_13", "ean_8", "code_128", "code_39", "upc_a", "upc_e", "itf"],
                });
                const codes = await detector.detect(canvas);
                if (codes.length && codes[0].rawValue) {
                    return codes[0].rawValue;
                }
            } catch (err) {
                // Fallback ZXing below.
            }
        }
        const ZXing = await ensureZXing();
        return decodeCanvasWithZXing(ZXing, canvas);
    }

    async lookup(code) {
        const scanned = (code || "").trim();
        if (!scanned || this.state.loading) {
            return;
        }
        this.state.loading = true;
        this.state.searched = true;
        this.state.scanned = scanned;
        try {
            const result = await this.orm.call("ctkm.barcode.lookup", "lookup_code", [scanned]);
            this.state.found = Boolean(result.found);
            this.state.matches = result.matches || [];
            this.state.scanned = result.scanned || scanned;
        } catch (err) {
            this.state.found = false;
            this.state.matches = [];
            this.notification.add(err.data?.message || err.message || _t("Không tra cứu được mã."), {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
            this.inputRef.el?.focus();
            this.inputRef.el?.select();
        }
    }

    onOpenProgram(ev) {
        const programId = Number(ev.currentTarget.dataset.programId);
        if (!programId) {
            return;
        }
        this.openProgram({ program_id: programId });
    }

    openProgram(match) {
        if (!match?.program_id) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "ctkm.program",
            res_id: match.program_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    get groups() {
        const groups = [];
        const indexByKey = {};
        for (const match of this.state.matches) {
            const key = `${match.program_id}::${match.material_code || ""}`;
            if (indexByKey[key] === undefined) {
                indexByKey[key] = groups.length;
                groups.push({
                    program_id: match.program_id,
                    program_name: match.program_name,
                    notify_code: match.notify_code,
                    date_begin: match.date_begin,
                    date_end: match.date_end,
                    material_code: match.material_code,
                    barcode: match.barcode,
                    promo_price: match.promo_price,
                    tem_tag: match.tem_tag,
                    lines: [],
                });
            }
            groups[indexByKey[key]].lines.push(match);
        }
        return groups;
    }
}

registry.category("actions").add("ctkm_barcode_scan", CtkmBarcodeScan);
