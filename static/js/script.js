/* ==================================================
   GLOBAL VARIABLES
================================================== */

let lastFailedOrderId = null;

let paymentFailureHandled = false;

let retryAttemptsCount = 0;


/* ==================================================
   PAGE LOAD
================================================== */

document.addEventListener(
    "DOMContentLoaded",
    function() {

        loadDashboard();

    }
);


/* ==================================================
   LOAD DASHBOARD
================================================== */

async function loadDashboard() {

    try {

        await Promise.all([

            loadStats(),

            loadPayments()

        ]);

    }

    catch (error) {

        console.error(
            "Dashboard error:",
            error
        );

    }

}


/* ==================================================
   LOAD STATISTICS
================================================== */

async function loadStats() {

    const response =
        await fetch(
            "/payment-stats"
        );


    const data =
        await response.json();


    if (!data) {
        return;
    }


    document.getElementById(
        "totalPayments"
    ).innerText =
        data.total_payments || 0;


    document.getElementById(
        "successfulPayments"
    ).innerText =
        data.successful_payments || 0;


    document.getElementById(
        "failedPayments"
    ).innerText =
        data.failed_payments || 0;


    document.getElementById(
        "recoveryRate"
    ).innerText =
        data.recovery_rate || "0%";

}


/* ==================================================
   LOAD PAYMENTS
================================================== */

async function loadPayments() {

    const response =
        await fetch(
            "/payments"
        );


    const data =
        await response.json();


    if (!data.success) {
        return;
    }


    renderPaymentTable(
        data.payments
    );


    renderFailureAnalytics(
        data.payments
    );

}


/* ==================================================
   PAYMENT TABLE
================================================== */

function renderPaymentTable(
    payments
) {

    const table =
        document.getElementById(
            "paymentTable"
        );


    table.innerHTML = "";


    if (
        !payments ||
        payments.length === 0
    ) {

        table.innerHTML = `
            <tr>
                <td
                    colspan="4"
                    class="empty"
                >
                    No payments found.
                </td>
            </tr>
        `;

        return;
    }


    payments.forEach(
        function(payment) {

            let statusClass =
                "status-created";


            if (
                payment.status ===
                "SUCCESS"
            ) {

                statusClass =
                    "status-success";

            }


            else if (
                payment.status ===
                "FAILED"
            ) {

                statusClass =
                    "status-failed";

            }

            else if (
                payment.status ===
                "RECOVERED"
            ) {

                statusClass =
                    "status-success";

            }


            const row =
                document.createElement(
                    "tr"
                );


            row.innerHTML = `

                <td>
                    ${escapeHtml(
                        payment.order_id ||
                        "-"
                    )}
                </td>

                <td>
                    ₹${formatAmount(
                        payment.amount
                    )}
                </td>

                <td>

                    <span
                        class="status ${statusClass}"
                    >
                        ${escapeHtml(
                            payment.status ||
                            "UNKNOWN"
                        )}
                    </span>

                </td>

                <td>
                    ${escapeHtml(
                        payment.failure_reason ||
                        "-"
                    )}
                </td>

            `;


            table.appendChild(
                row
            );

        }
    );

}


/* ==================================================
   FAILURE ANALYTICS
================================================== */

function renderFailureAnalytics(
    payments
) {

    const container =
        document.getElementById(
            "failureAnalytics"
        );


    const failures = {};


    payments.forEach(
        function(payment) {

            if (
                payment.status !==
                "FAILED"
            ) {

                return;

            }


            const reason =
                payment.failure_reason ||
                "Unknown Failure";


            let category =
                getFailureCategory(
                    reason
                );


            if (
                !failures[category]
            ) {

                failures[category] = 0;

            }


            failures[category]++;

        }
    );


    const categories =
        Object.keys(
            failures
        );


    if (
        categories.length === 0
    ) {

        container.innerHTML = `
            <div class="empty">
                No failed payments yet.
            </div>
        `;

        return;
    }


    container.innerHTML = "";


    categories
        .sort(
            function(a, b) {

                return (
                    failures[b] -
                    failures[a]
                );

            }
        )
        .forEach(
            function(category) {

                const item =
                    document.createElement(
                        "div"
                    );


                item.className =
                    "failure-item";


                item.innerHTML = `

                    <span class="failure-name">
                        ${escapeHtml(
                            category
                        )}
                    </span>

                    <span class="failure-count">
                        ${failures[category]}
                    </span>

                `;


                container.appendChild(
                    item
                );

            }
        );

}


/* ==================================================
   FAILURE CATEGORY
================================================== */

function getFailureCategory(
    reason
) {

    const text =
        reason.toLowerCase();


    if (
        text.includes("declined") ||
        text.includes("bank")
    ) {

        return "BANK_DECLINED";

    }


    if (
        text.includes("insufficient") ||
        text.includes("balance")
    ) {

        return "INSUFFICIENT_BALANCE";

    }


    if (
        text.includes("timeout") ||
        text.includes("timed out")
    ) {

        return "TIMEOUT";

    }


    if (
        text.includes("network") ||
        text.includes("connection")
    ) {

        return "NETWORK_ERROR";

    }


    if (
        text.includes("cancel") ||
        text.includes("closed")
    ) {

        return "USER_CANCELLED";

    }


    return "UNKNOWN";

}


/* ==================================================
   CREATE ORDER
================================================== */

async function createOrder(recoveryOrderId = null) {

    if (recoveryOrderId === null) {
        retryAttemptsCount = 0;
        document.getElementById("escalationStatus").style.display = "none";
        const retryBtn = document.querySelector(".retry-button");
        if (retryBtn) {
            retryBtn.disabled = false;
            retryBtn.innerText = "Retry Payment";
        }
    }

    const amount =
        parseFloat(
            document.getElementById(
                "amount"
            ).value
        );


    hideRecovery();


    if (
        !amount ||
        amount <= 0
    ) {

        showMessage(
            "Please enter a valid amount.",
            "error"
        );

        return;
    }


    try {

        disablePayButton(
            true
        );


        showMessage(
            "Creating Razorpay order...",
            "info"
        );


        paymentFailureHandled =
            false;


        const response =
            await fetch(
                "/create-order",
                {

                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            amount: amount,
                            recovery_of_order_id: recoveryOrderId
                        })

                }
            );


        const data =
            await response.json();


        if (!data.success) {

            showMessage(
                data.error ||
                "Unable to create order.",
                "error"
            );

            disablePayButton(
                false
            );

            return;
        }


        /* RAZORPAY */

        const options = {

            key:
                data.key_id,

            amount:
                data.amount,

            currency:
                data.currency,

            name:
                "AI Payment Recovery",

            description:
                "Test Payment",

            order_id:
                data.order_id,


            handler:
                async function(
                    response
                ) {

                    await verifyPayment(
                        response
                    );

                },


            modal: {

                ondismiss:
                    function() {

                        if (
                            paymentFailureHandled
                        ) {

                            return;

                        }


                        showMessage(
                            "Payment window closed.",
                            "error"
                        );


                        disablePayButton(
                            false
                        );

                    }

            }

        };


        const razorpay =
            new Razorpay(
                options
            );


        razorpay.on(
            "payment.failed",
            async function(
                response
            ) {

                paymentFailureHandled =
                    true;


                const error =
                    response.error ||
                    {};


                const description =
                    error.description ||
                    "Payment failed";


                const errorCode =
                    error.code ||
                    "PAYMENT_FAILED";


                lastFailedOrderId =
                    data.order_id;


                try {

                    razorpay.close();

                }

                catch (e) {

                    console.log(
                        "Checkout already closed."
                    );

                }


                await new Promise(
                    function(resolve) {

                        setTimeout(
                            resolve,
                            300
                        );

                    }
                );


                await handlePaymentFailure(

                    data.order_id,

                    description,

                    errorCode

                );


                disablePayButton(
                    false
                );


                /*
                 * Refresh dashboard so
                 * FAILED status appears.
                 */

                await loadDashboard();

            }
        );


        razorpay.open();

    }


    catch (error) {

        console.error(
            error
        );


        showMessage(
            "Something went wrong while creating the payment.",
            "error"
        );


        disablePayButton(
            false
        );

    }

}


/* ==================================================
   VERIFY PAYMENT
================================================== */

async function verifyPayment(
    response
) {

    try {

        showMessage(
            "Verifying payment...",
            "info"
        );


        const verifyResponse =
            await fetch(
                "/verify-payment",
                {

                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            razorpay_order_id:
                                response
                                    .razorpay_order_id,

                            razorpay_payment_id:
                                response
                                    .razorpay_payment_id,

                            razorpay_signature:
                                response
                                    .razorpay_signature

                        })

                }
            );


        const result =
            await verifyResponse.json();


        if (
            result.success
        ) {

            showMessage(

                result.recovered
                    ? "Payment Recovered Successfully! Payment ID: " + result.payment_id
                    : "Payment Successful! Payment ID: " + result.payment_id,

                "success"

            );


            hideRecovery();


            /*
             * Refresh dashboard.
             */

            await loadDashboard();

        }


        else {

            showMessage(
                "Payment verification failed.",
                "error"
            );

        }

    }


    catch (error) {

        console.error(
            error
        );


        showMessage(
            "Payment verification error.",
            "error"
        );

    }


    finally {

        disablePayButton(
            false
        );

    }

}


/* ==================================================
   HANDLE FAILURE
================================================== */

async function handlePaymentFailure(

    orderId,

    errorDescription,

    errorCode

) {

    hideRecovery();


    showMessage(
        "Payment failed. Analyzing the failure...",
        "error"
    );


    try {

        /* FAILURE ANALYSIS */

        const analysisResponse =
            await fetch(
                "/analyze-failure",
                {

                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            razorpay_order_id:
                                orderId,

                            error_description:
                                errorDescription,

                            error_code:
                                errorCode

                        })

                }
            );


        const analysis =
            await analysisResponse.json();


        if (
            !analysis.success
        ) {

            showMessage(
                analysis.error ||
                "Unable to analyze payment failure.",
                "error"
            );

            return;
        }


        /* RECOVERY ENGINE */

        const recoveryResponse =
            await fetch(
                "/recovery-recommendation",
                {

                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            razorpay_order_id:
                                orderId,

                            failure_category:
                                analysis.category,

                            severity:
                                analysis.severity,

                            failure_reason:
                                analysis.failure_reason

                        })

                }
            );


        const recovery =
            await recoveryResponse.json();


        if (
            !recovery.success
        ) {

            showMessage(
                "Recovery recommendation failed.",
                "error"
            );

            return;
        }


        showRecoveryCard(
            analysis,
            recovery
        );


        showMessage(
            "Payment failed. Recovery recommendation generated.",
            "error"
        );

    }


    catch (error) {

        console.error(
            error
        );


        showMessage(
            "Unable to generate recovery recommendation.",
            "error"
        );

    }

}


/* ==================================================
   RECOVERY CARD
================================================== */

function showRecoveryCard(
    analysis,
    recovery
) {

    document.getElementById(
        "recoveryCard"
    ).style.display =
        "block";


    document.getElementById(
        "failureReason"
    ).innerText =
        analysis.failure_reason ||
        "Payment failed";


    document.getElementById(
        "failureCategory"
    ).innerText =
        analysis.category ||
        recovery.failure_category ||
        "UNKNOWN";


    document.getElementById(
        "recommendedMethod"
    ).innerText =
        recovery.recommended_payment_method ||
        "UPI";


    document.getElementById(
        "priority"
    ).innerText =
        recovery.priority ||
        "MEDIUM";


    document.getElementById(
        "recoveryMessage"
    ).innerText =
        analysis.recommendation ||
        recovery.message ||
        "Please try the payment again.";

    document.getElementById(
        "recoveryMessageHinglish"
    ).innerText =
        analysis.recommendation_hinglish ||
        "Payment fail ho gaya hai. Kripya doosra card ya UPI account use karein.";

}


/* ==================================================
   RETRY
================================================== */

function retryPayment() {

    const amount =
        parseFloat(
            document.getElementById(
                "amount"
            ).value
        );


    if (
        !amount ||
        amount <= 0
    ) {

        showMessage(
            "Please enter a valid amount.",
            "error"
        );

        return;
    }

    retryAttemptsCount++;
    if (retryAttemptsCount >= 3) {
        document.getElementById("escalationStatus").style.display = "block";
        const retryBtn = document.querySelector(".retry-button");
        if (retryBtn) {
            retryBtn.disabled = true;
            retryBtn.innerText = "Escalated to Support";
        }
        showMessage("Max retry limit reached. This case has been escalated to support.", "error");
        return;
    }

    hideRecovery();


    showMessage(
        "Starting payment retry (Attempt " + retryAttemptsCount + "/3)...",
        "info"
    );


    setTimeout(
        function() {

            createOrder(lastFailedOrderId);

        },
        500
    );

}


/* ==================================================
   HELPERS
================================================== */

function showMessage(
    text,
    type
) {

    const message =
        document.getElementById(
            "message"
        );


    message.innerText =
        text;


    message.className =
        type;


    message.style.display =
        "block";

}


function hideRecovery() {

    document.getElementById(
        "recoveryCard"
    ).style.display =
        "none";

}


function disablePayButton(
    disabled
) {

    const button =
        document.getElementById(
            "payButton"
        );


    button.disabled =
        disabled;


    button.innerText =
        disabled
            ? "Processing..."
            : "Pay Now";

}


function formatAmount(
    amount
) {

    const number =
        Number(amount || 0);


    return number.toLocaleString(
        "en-IN",
        {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }
    );

}


function escapeHtml(
    value
) {

    const div =
        document.createElement(
            "div"
        );


    div.innerText =
        value == null
            ? ""
            : String(value);


    return div.innerHTML;

}

/* ==================================================
   SIMULATION & EXPORT INTERFACE handlers
   ================================================== */

async function runBatchSimulation() {
    const btn = document.getElementById("batchSimButton");
    btn.disabled = true;
    btn.innerText = "Running Sim...";
    
    try {
        const response = await fetch("/simulate-batch", { method: "POST" });
        const data = await response.json();
        if (data.success) {
            showMessage("Simulated 10 transactions successfully!", "success");
            await loadDashboard();
        } else {
            showMessage("Simulation failed: " + data.error, "error");
        }
    } catch (e) {
        showMessage("Simulation error: " + e.message, "error");
    } finally {
        btn.disabled = false;
        btn.innerText = "Run Batch Simulation";
    }
}

function exportAuditTrail() {
    window.open("/export-audit", "_blank");
}
