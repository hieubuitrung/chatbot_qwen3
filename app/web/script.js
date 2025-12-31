$(document).ready(function () {
  let attachments = [];

  // Mở/đóng popup
  $("#chatButton").on("click", function () {
    $("#chatPopup").toggleClass("active");
    if ($("#chatPopup").hasClass("active")) {
      $("#messageInput").focus();
      const currentConvId = getConversationId();
      loadChatHistory(currentConvId);
    }
  });

  $("#closeBtn").on("click", function () {
    $("#chatPopup").removeClass("active");
  });

  // Auto-resize textarea
  $("#messageInput").on("input", function () {
    this.style.height = "auto";
    this.style.height = Math.min(this.scrollHeight, 100) + "px";
  });

  // Gửi tin nhắn khi nhấn Enter
  $("#messageInput").on("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  $("#sendBtn").on("click", function (e) {
    e.preventDefault();
    sendMessage();
  });

  $("#stopBtn").on("click", function (e) {
    e.preventDefault();
    stopGeneration();
  });

  // Xử lý attach file
  $("#attachFileBtn").on("click", function () {
    $("#fileInput").click();
  });

  $("#attachImageBtn").on("click", function () {
    $("#imageInput").click();
  });

  $("#fileInput, #imageInput").on("change", function (e) {
    handleFileSelect(
      e.target.files,
      $(this).attr("id") === "imageInput" ? "image" : "file"
    );
    $(this).val(""); // Reset input
  });

  function handleFileSelect(files, type) {
    Array.from(files).forEach((file) => {
      const reader = new FileReader();
      reader.onload = function (e) {
        const attachment = {
          name: file.name,
          type: type,
          preview: type === "image" ? e.target.result : null,
          file: file,
        };
        attachments.push(attachment);
        renderAttachmentsPreview();
      };
      reader.readAsDataURL(file);
    });
  }

  function renderAttachmentsPreview() {
    const $preview = $("#attachmentsPreview");
    $preview.empty();

    if (attachments.length > 0) {
      $preview.addClass("active");
      attachments.forEach((att, index) => {
        const $item = $("<div>").addClass(`attachment-item ${att.type}`);

        if (att.type === "image") {
          $item.append($("<img>").attr("src", att.preview));
        } else {
          $item.append($("<i>").addClass("fas fa-file"));
          $item.append($("<span>").text(att.name));
        }

        const $removeBtn = $("<button>")
          .addClass("remove-attachment")
          .html('<i class="fas fa-times"></i>')
          .on("click", function () {
            attachments.splice(index, 1);
            renderAttachmentsPreview();
          });

        $item.append($removeBtn);
        $preview.append($item);
      });
    } else {
      $preview.removeClass("active");
    }
  }

  async function loadChatHistory(conversationId, limit = 20) {
    const apiUrl = `http://localhost:8000/chat/history?conversation_id=${conversationId}&limit=${limit}`;

    // Hiển thị trạng thái đang tải (tùy chọn)
    $("#typingIndicator").addClass("active");

    try {
      const response = await fetch(apiUrl, {
        method: "GET",
        headers: { accept: "application/json" },
      });

      if (!response.ok) throw new Error("Không thể lấy lịch sử");

      const history = await response.json();

      // Xóa nội dung cũ trong khung chat nếu cần (để tránh lặp tin nhắn)
      // $(".message").remove();

      // Lặp qua từng tin nhắn trong lịch sử
      history.messages.forEach((item) => {
        const isUser = item.role === "user";
        const content = item.content || "";
        // Đảm bảo attachments đúng định dạng mảng để addMessage không lỗi
        const attachments = item.attachments || [];

        // Gọi hàm addMessage có sẵn của bạn
        addMessage(content, isUser, attachments);
      });
    } catch (error) {
      console.error("Lỗi render lịch sử:", error);
      addMessage("Không thể tải lịch sử trò chuyện.", false);
    } finally {
      $("#typingIndicator").removeClass("active");
      scrollToBottom();
    }
  }

  // Hàm thêm tin nhắn vào chat
  function addMessage(content, isUser = false, attachmentsData = []) {
    const $messageDiv = $("<div>").addClass(
      `message ${isUser ? "user" : "bot"}`
    );
    const $contentDiv = $("<div>").addClass("message-content");

    const $textDiv = $("<div>").addClass("message-text");
    if (content) {
      $textDiv.text(content);
    }
    $contentDiv.append($textDiv);

    if (attachmentsData.length > 0) {
      const $attachmentsDiv = $("<div>").addClass("message-attachments");

      attachmentsData.forEach((att) => {
        const $attDiv = $("<div>").addClass(`message-attachment ${att.type}`);

        if (att.type === "image" && att.preview) {
          const $img = $("<img>").attr("src", att.preview);
          $img.on("click", function () {
            window.open(att.preview, "_blank");
          });
          $attDiv.append($img);
        } else {
          $attDiv.append($("<i>").addClass("fas fa-file"));
          $attDiv.append($("<span>").text(att.name));
        }

        $attachmentsDiv.append($attDiv);
      });

      $contentDiv.append($attachmentsDiv);
    }

    $messageDiv.append($contentDiv);
    $("#typingIndicator").before($messageDiv);
    scrollToBottom();

    return $textDiv;
  }

  function scrollToBottom() {
    const $chatMessages = $("#chatMessages");
    $chatMessages.scrollTop($chatMessages.prop("scrollHeight"));
  }

  async function sendMessage() {
    const message = $("#messageInput").val().trim();
    if (!message && attachments.length === 0) return;

    const userAttachments = [...attachments];
    addMessage(message, true, userAttachments);

    $("#messageInput").val("").css("height", "auto");
    attachments = [];
    renderAttachmentsPreview();

    $(
      "#stopBtn, #messageInput, #attachFileBtn, #attachImageBtn, #voiceBtn"
    ).prop("disabled", true);
    $("#sendBtn").addClass("d-none");
    $("#stopBtn").removeClass("d-none");
    $("#typingIndicator").addClass("active");

    try {
      const response = await fetch("http://127.0.0.1:8000/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          conversation_id: getConversationId(),
          message: message,
        }),
      });

      if (!response.ok) {
        throw new Error("API request failed: " + response.status);
      }

      let $botMessageContent = null;
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let fullText = "";
      let firstChunk = true;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        fullText += chunk;

        if (firstChunk && chunk.trim() !== "") {
          $("#typingIndicator").removeClass("active");
          $("#stopBtn").prop("disabled", false);
          $botMessageContent = addMessage("", false);
          firstChunk = false;
        }

        $botMessageContent.text(fullText);
        // scrollToBottom();
      }

      // 1. Chuyển Markdown thành HTML bằng marked
      // let htmlContent = marked.parse(fullText);

      // 2. Gán HTML vào phần tử Chat
      // $botMessageContent.html(htmlContent);

      // scrollToBottom();
    } catch (error) {
      console.error("Error:", error);
      $("#typingIndicator").removeClass("active");
      addMessage("Xin lỗi, có lỗi xảy ra. Vui lòng thử lại sau.", false);
    } finally {
      $(
        "#stopBtn, #messageInput, #attachFileBtn, #attachImageBtn, #voiceBtn"
      ).prop("disabled", false);
      $("#stopBtn").addClass("d-none");
      $("#sendBtn").removeClass("d-none");
      $("#messageInput").focus();
    }
  }

  async function stopGeneration() {
    const conversationId = getConversationId(); // bạn đang dùng rồi

    try {
      await fetch("http://127.0.0.1:8000/stop", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          conversation_id: conversationId,
        }),
      });

      console.log("Generation stop requested");
    } catch (err) {
      console.error("Stop generation error:", err);
    }
  }

  function getConversationId() {
    let conversationId = sessionStorage.getItem("conversation_id");
    if (!conversationId) {
      conversationId =
        "conv_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9);
      sessionStorage.setItem("conversation_id", conversationId);
    }
    return conversationId;
  }

  // Voice recording placeholder
  $("#voiceBtn").on("click", function () {
    $(this).toggleClass("recording");
    if ($(this).hasClass("recording")) {
      console.log("Recording started...");
    } else {
      console.log("Recording stopped.");
    }
  });
});
