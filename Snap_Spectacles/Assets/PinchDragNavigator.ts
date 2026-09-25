import { SIK } from "SpectaclesInteractionKit.lspkg/SIK";

@component
export class PinchDragNavigator extends BaseScriptComponent {

    // ---------- Inspector inputs ----------

    @input
    arrowObject: SceneObject;

    @input
    arrowTransform: ScreenTransform;

    @input
    arrowText: Text;

    @input
    statusText: Text;

    // false = right hand
    // true  = left hand
    @input
    useLeftHand: boolean = false;

    // Minimum drag before movement starts
    @input
    deadzoneScreen: number = 0.03;

    // Drag distance corresponding to 100% command
    @input
    maxDragScreen: number = 0.18;

    // Robot command limits
    @input
    maxLinearSpeed: number = 0.3;   // m/s

    @input
    maxAngularSpeed: number = 0.5;  // rad/s


    // ---------- Audio feedback ----------

    @input
    startAudio: AudioComponent;

    @input
    endAudio: AudioComponent;

    @input
    startSound: AudioTrackAsset;

    @input
    endSound: AudioTrackAsset;


    // ---------- Public robot command ----------

    public currentVx: number = 0;
    public currentWz: number = 0;
    public isActive: boolean = false;


    // ---------- Internal state ----------

    private hand = SIK.HandInputData.getHand("right");

    private wasPinching: boolean = false;

    private anchorScreenPos: vec2 = null;

    private baseArrowScale: vec3 = new vec3(1, 1, 1);


    onAwake() {

        // Select hand
        this.hand = SIK.HandInputData.getHand(
            this.useLeftHand ? "left" : "right"
        );

        // Remember the arrow's original scale
        if (this.arrowTransform) {
            this.baseArrowScale = this.arrowTransform.scale;
        }

        // Wire up audio feedback sounds
        if (this.startAudio && this.startSound) {
            this.startAudio.audioTrack = this.startSound;
        }

        if (this.endAudio && this.endSound) {
            this.endAudio.audioTrack = this.endSound;
        }

        // Start stopped
        this.stopCommand();

        // Run every frame
        this.createEvent("UpdateEvent").bind(() => {
            this.onUpdate();
        });
    }


    // ----------------------------------------------------
    // HAND INPUT
    // ----------------------------------------------------

    private getPinchScreenPos(): vec2 {

        if (!this.hand) {
            return null;
        }

        if (!this.hand.isTracked()) {
            return null;
        }

        if (!this.hand.isPinching()) {
            return null;
        }

        // SIK already gives us screen-space coordinates
        return this.hand.indexTip.screenPosition;
    }


    // ----------------------------------------------------
    // MAIN LOOP
    // ----------------------------------------------------

    private onUpdate() {

        const pinchPos = this.getPinchScreenPos();

        const isPinchingNow = pinchPos !== null;


        // -----------------------------
        // PINCH JUST STARTED
        // -----------------------------

        if (isPinchingNow && !this.wasPinching) {

            // Store where the pinch started.
            // This becomes the virtual joystick centre.
            this.anchorScreenPos = pinchPos;

            this.stopCommand();

            this.playStartSound();
        }


        // -----------------------------
        // PINCH IS BEING HELD
        // -----------------------------

        else if (
            isPinchingNow &&
            this.anchorScreenPos !== null
        ) {

            this.updateDirection(pinchPos);
        }


        // -----------------------------
        // PINCH RELEASED / HAND LOST
        // -----------------------------

        else if (!isPinchingNow) {

            if (this.wasPinching) {
                this.playEndSound();
            }

            this.anchorScreenPos = null;

            this.stopCommand();
        }


        this.wasPinching = isPinchingNow;
    }


    // ----------------------------------------------------
    // JOYSTICK MATH
    // ----------------------------------------------------

    private updateDirection(pinchPos: vec2) {

        if (this.anchorScreenPos === null) {
            return;
        }


        // Horizontal movement
        const dragX =
            pinchPos.x -
            this.anchorScreenPos.x;


        // Lens screen Y increases downward,
        // so invert it:
        //
        // hand up   = positive forward
        // hand down = negative forward

        const dragY =
            this.anchorScreenPos.y -
            pinchPos.y;


        const dragLen =
            Math.sqrt(
                dragX * dragX +
                dragY * dragY
            );


        // -----------------------------
        // DEADZONE
        // -----------------------------

        if (dragLen < this.deadzoneScreen) {

            // IMPORTANT:
            // stopCommand() does NOT delete
            // the joystick anchor.

            this.stopCommand();

            return;
        }


        // Protect against division by zero / bad settings
        const usableRange =
            Math.max(
                this.maxDragScreen -
                this.deadzoneScreen,
                0.001
            );


        let magnitude01 =
            (dragLen - this.deadzoneScreen) /
            usableRange;


        magnitude01 =
            Math.max(
                0,
                Math.min(magnitude01, 1)
            );


        // Direction vector
        const directionX = dragX / dragLen;
        const directionY = dragY / dragLen;


        // ------------------------------------------------
        // ROBOT COMMAND
        //
        // drag up    -> +linear.x
        // drag down  -> -linear.x
        //
        // drag left  -> +angular.z
        // drag right -> -angular.z
        // ------------------------------------------------

        this.currentVx =
            directionY *
            magnitude01 *
            this.maxLinearSpeed;


        this.currentWz =
            -directionX *
            magnitude01 *
            this.maxAngularSpeed;


        this.isActive = true;


        // ------------------------------------------------
        // ARROW DIRECTION
        //
        // Arrow should point UP in its default orientation.
        // ------------------------------------------------

        const angleRad =
            Math.atan2(
                dragX,
                dragY
            );


        this.drawArrow(
            angleRad,
            magnitude01
        );


        this.updateStatusText(
            magnitude01
        );
    }


    // ----------------------------------------------------
    // STOP
    // ----------------------------------------------------

    private stopCommand() {

        this.currentVx = 0;

        this.currentWz = 0;

        this.isActive = false;


        this.drawArrow(
            0,
            0
        );


        this.updateStatusText(
            0
        );
    }


    // ----------------------------------------------------
    // AUDIO FEEDBACK
    // ----------------------------------------------------

    private playStartSound() {
        if (this.startAudio && this.startSound) {
            this.startAudio.play(1);
        }
    }

    private playEndSound() {
        if (this.endAudio && this.endSound) {
            this.endAudio.play(1);
        }
    }


    // ----------------------------------------------------
    // ARROW VISUAL
    // ----------------------------------------------------

    private drawArrow(
        angleRad: number,
        magnitude01: number
    ) {

        if (
            !this.arrowObject ||
            !this.arrowTransform
        ) {
            return;
        }


        // Arrow is glass-locked (child of the tracked Camera's
        // Screen Transform) and always stays on screen.
        this.arrowObject.enabled = true;


        if (magnitude01 > 0) {

            // Actively pinching/dragging: show the arrow,
            // pointed toward the drag direction.

            if (this.arrowText) {
                this.arrowText.text = "↑"; // ↑
            }

            this.arrowTransform.rotation =
                quat.fromEulerAngles(
                    0,
                    0,
                    -angleRad
                );


            // Arrow grows as the command increases
            const scaleMultiplier =
                0.7 +
                magnitude01 * 0.7;


            this.arrowTransform.scale =
                new vec3(
                    this.baseArrowScale.x * scaleMultiplier,
                    this.baseArrowScale.y * scaleMultiplier,
                    this.baseArrowScale.z
                );

        } else {

            // Not pinching: collapse to a dot showing "no movement".

            if (this.arrowText) {
                this.arrowText.text = "●"; // ●
            }

            this.arrowTransform.rotation =
                quat.fromEulerAngles(0, 0, 0);

            this.arrowTransform.scale =
                new vec3(
                    this.baseArrowScale.x * 0.7,
                    this.baseArrowScale.y * 0.7,
                    this.baseArrowScale.z
                );
        }
    }


    // ----------------------------------------------------
    // DEBUG TEXT
    // ----------------------------------------------------

    private updateStatusText(
        magnitude01: number
    ) {

        if (!this.statusText) {
            return;
        }


        if (magnitude01 <= 0) {

            this.statusText.text =
                "STOPPED";

            return;
        }


        const speedPercent =
            Math.round(
                magnitude01 * 100
            );


        this.statusText.text =
            "Speed: " +
            speedPercent +
            "%\n" +
            "vx: " +
            this.currentVx.toFixed(2) +
            " m/s\n" +
            "wz: " +
            this.currentWz.toFixed(2) +
            " rad/s";
    }
}
