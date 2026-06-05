function SrsRtcWhipWhepAsync() {
  this.play = async function(url) {
    console.log("Mock SRS WHEP play:", url);
    return Promise.resolve();
  };
  this.close = function() {
    console.log("Mock SRS WHEP close");
  };
}
window.SrsRtcWhipWhepAsync = SrsRtcWhipWhepAsync;
