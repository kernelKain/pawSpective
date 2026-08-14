export type CanineVisionRenderer = {
  start: () => void;
  stop: () => void;
  destroy: () => void;
  setMix: (mix: number) => void;
  setDetailReduction: (amount: number) => void;
  setMirror: (mirror: boolean) => void;
};

const vertexShaderSource = `
  attribute vec2 a_position;
  attribute vec2 a_texCoord;

  uniform float u_mirror;

  varying vec2 v_texCoord;

  void main() {
    gl_Position = vec4(a_position, 0.0, 1.0);

    float textureX = mix(
      a_texCoord.x,
      1.0 - a_texCoord.x,
      u_mirror
    );

    v_texCoord = vec2(textureX, a_texCoord.y);
  }
`;

const fragmentShaderSource = `
  precision mediump float;

  uniform sampler2D u_video;
  uniform vec2 u_resolution;
  uniform float u_mix;
  uniform float u_detailReduction;

  varying vec2 v_texCoord;

  vec3 toLinear(vec3 color) {
    return pow(color, vec3(2.2));
  }

  vec3 toSrgb(vec3 color) {
    return pow(max(color, vec3(0.0)), vec3(1.0 / 2.2));
  }

  vec3 canineApproximation(vec3 sourceColor) {
    vec3 linearColor = toLinear(sourceColor);

    /*
      Engineering approximation for reducing red/green separation.

      These coefficients are a display transform, not a claim that an RGB
      screen can reconstruct canine spectral perception exactly.
    */
    vec3 transformed = vec3(
      0.367322 * linearColor.r +
      0.860646 * linearColor.g -
      0.227968 * linearColor.b,

      0.280085 * linearColor.r +
      0.672501 * linearColor.g +
      0.047413 * linearColor.b,

      -0.011820 * linearColor.r +
      0.042940 * linearColor.g +
      0.968881 * linearColor.b
    );

    return toSrgb(clamp(transformed, 0.0, 1.0));
  }

  void main() {
    vec2 pixel = 1.0 / max(u_resolution, vec2(1.0));

    vec3 center = texture2D(u_video, v_texCoord).rgb;

    vec3 nearbyAverage = (
      center +
      texture2D(u_video, v_texCoord + vec2(pixel.x, 0.0)).rgb +
      texture2D(u_video, v_texCoord - vec2(pixel.x, 0.0)).rgb +
      texture2D(u_video, v_texCoord + vec2(0.0, pixel.y)).rgb +
      texture2D(u_video, v_texCoord - vec2(0.0, pixel.y)).rgb
    ) / 5.0;

    vec3 reducedDetail = mix(
      center,
      nearbyAverage,
      u_detailReduction
    );

    vec3 dogView = canineApproximation(reducedDetail);

    gl_FragColor = vec4(
      mix(center, dogView, u_mix),
      1.0
    );
  }
`;

function clamp(value: number, minimum = 0, maximum = 1): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function createShader(
  gl: WebGLRenderingContext,
  type: number,
  source: string,
): WebGLShader {
  const shader = gl.createShader(type);

  if (!shader) {
    throw new Error("Unable to create a WebGL shader.");
  }

  gl.shaderSource(shader, source);
  gl.compileShader(shader);

  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const message =
      gl.getShaderInfoLog(shader) ?? "Unknown WebGL shader error.";

    gl.deleteShader(shader);
    throw new Error(message);
  }

  return shader;
}

function createProgram(
  gl: WebGLRenderingContext,
  vertexShader: WebGLShader,
  fragmentShader: WebGLShader,
): WebGLProgram {
  const program = gl.createProgram();

  if (!program) {
    throw new Error("Unable to create the WebGL program.");
  }

  gl.attachShader(program, vertexShader);
  gl.attachShader(program, fragmentShader);
  gl.linkProgram(program);

  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const message =
      gl.getProgramInfoLog(program) ?? "Unknown WebGL program error.";

    gl.deleteProgram(program);
    throw new Error(message);
  }

  return program;
}

export function createCanineVisionRenderer(
  canvas: HTMLCanvasElement,
  video: HTMLVideoElement,
): CanineVisionRenderer {
  const context = canvas.getContext("webgl", {
    alpha: false,
    antialias: false,
    preserveDrawingBuffer: false,
    powerPreference: "high-performance",
  });

  if (!context) {
    throw new Error(
      "WebGL is unavailable. Enable hardware acceleration or use a modern browser.",
    );
  }

  // Copy the checked context into a non-null binding so TypeScript keeps the
  // guarantee inside the renderer's nested animation callbacks.
  const gl: WebGLRenderingContext = context;

  const vertexShader = createShader(
    gl,
    gl.VERTEX_SHADER,
    vertexShaderSource,
  );

  const fragmentShader = createShader(
    gl,
    gl.FRAGMENT_SHADER,
    fragmentShaderSource,
  );

  const program = createProgram(gl, vertexShader, fragmentShader);
  gl.useProgram(program);

  const positionLocation = gl.getAttribLocation(program, "a_position");
  const textureLocation = gl.getAttribLocation(program, "a_texCoord");

  const mixLocation = gl.getUniformLocation(program, "u_mix");
  const resolutionLocation = gl.getUniformLocation(
    program,
    "u_resolution",
  );
  const detailLocation = gl.getUniformLocation(
    program,
    "u_detailReduction",
  );
  const mirrorLocation = gl.getUniformLocation(program, "u_mirror");
  const videoLocation = gl.getUniformLocation(program, "u_video");

  if (
    positionLocation < 0 ||
    textureLocation < 0 ||
    mixLocation === null ||
    resolutionLocation === null ||
    detailLocation === null ||
    mirrorLocation === null ||
    videoLocation === null
  ) {
    throw new Error("The Dog Vision renderer could not be initialized.");
  }

  const vertexBuffer = gl.createBuffer();

  if (!vertexBuffer) {
    throw new Error("Unable to create the WebGL vertex buffer.");
  }

  /*
    Each vertex contains:
    position x, position y, texture x, texture y
  */
  const vertices = new Float32Array([
    -1, -1, 0, 0,
     1, -1, 1, 0,
    -1,  1, 0, 1,

    -1,  1, 0, 1,
     1, -1, 1, 0,
     1,  1, 1, 1,
  ]);

  gl.bindBuffer(gl.ARRAY_BUFFER, vertexBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);

  const stride = 4 * Float32Array.BYTES_PER_ELEMENT;

  gl.enableVertexAttribArray(positionLocation);
  gl.vertexAttribPointer(
    positionLocation,
    2,
    gl.FLOAT,
    false,
    stride,
    0,
  );

  gl.enableVertexAttribArray(textureLocation);
  gl.vertexAttribPointer(
    textureLocation,
    2,
    gl.FLOAT,
    false,
    stride,
    2 * Float32Array.BYTES_PER_ELEMENT,
  );

  const texture = gl.createTexture();

  if (!texture) {
    throw new Error("Unable to create the video texture.");
  }

  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texParameteri(
    gl.TEXTURE_2D,
    gl.TEXTURE_WRAP_S,
    gl.CLAMP_TO_EDGE,
  );
  gl.texParameteri(
    gl.TEXTURE_2D,
    gl.TEXTURE_WRAP_T,
    gl.CLAMP_TO_EDGE,
  );
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);

  gl.uniform1i(videoLocation, 0);

  let animationFrame: number | null = null;
  let mix = 0.72;
  let detailReduction = 0.12;
  let mirror = false;

  function resizeCanvas(): void {
    if (!video.videoWidth || !video.videoHeight) {
      return;
    }

    // Limit internal rendering resolution for predictable mobile performance.
    const maximumWidth = 1280;
    const scale = Math.min(1, maximumWidth / video.videoWidth);

    const width = Math.max(1, Math.round(video.videoWidth * scale));
    const height = Math.max(1, Math.round(video.videoHeight * scale));

    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    gl.viewport(0, 0, canvas.width, canvas.height);
  }

  function render(): void {
    if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
      resizeCanvas();

      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, texture);

      gl.texImage2D(
        gl.TEXTURE_2D,
        0,
        gl.RGBA,
        gl.RGBA,
        gl.UNSIGNED_BYTE,
        video,
      );

      gl.uniform1f(mixLocation, mix);
      gl.uniform1f(detailLocation, detailReduction);
      gl.uniform1f(mirrorLocation, mirror ? 1 : 0);
      gl.uniform2f(
        resolutionLocation,
        canvas.width,
        canvas.height,
      );

      gl.drawArrays(gl.TRIANGLES, 0, 6);
    }

    animationFrame = window.requestAnimationFrame(render);
  }

  function start(): void {
    if (animationFrame === null) {
      animationFrame = window.requestAnimationFrame(render);
    }
  }

  function stop(): void {
    if (animationFrame !== null) {
      window.cancelAnimationFrame(animationFrame);
      animationFrame = null;
    }
  }

  function destroy(): void {
    stop();

    gl.deleteTexture(texture);
    gl.deleteBuffer(vertexBuffer);
    gl.deleteProgram(program);
    gl.deleteShader(vertexShader);
    gl.deleteShader(fragmentShader);
  }

  return {
    start,
    stop,
    destroy,

    setMix(value: number) {
      mix = clamp(value);
    },

    setDetailReduction(value: number) {
      detailReduction = clamp(value);
    },

    setMirror(value: boolean) {
      mirror = value;
    },
  };
}
