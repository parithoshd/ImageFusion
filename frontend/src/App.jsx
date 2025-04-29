// src/App.jsx
import { useState } from "react";
import axios from "axios";
import "tailwindcss";

export default function App() {
  const [images, setImages] = useState([
    { label: "Image 01", value: "" },
    { label: "Image 02", value: "" },
    { label: "Image 03", value: "" },
    { label: "Background (BG)", value: "" },
    { label: "Prop", value: "" },
  ]);
  const [prompt, setPrompt] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [loading, setLoading] = useState(false);
  // const [summary, setSummary] = useState([]);
  const [generatedPrompt, setGeneratedPrompt] = useState("");
  const [similarity, setSimilarity] = useState(null);

  const handleInputChange = (index, event) => {
    const updated = [...images];
    updated[index].value = event.target.value;
    setImages(updated);
  };

  const handleFileUpload = (index, event) => {
    const file = event.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        const updated = [...images];
        updated[index].value = reader.result; // Base64-encoded image
        setImages(updated);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleGenerate = async () => {
    const refs = images.map((img) => img.value).filter((v) => v);
    if (refs.length < 3) return alert("Please provide at least 3 images.");
    setLoading(true);
    try {
      const response = await axios.post("http://localhost:8000/generate", {
        prompt,
        refs,
      });
      setOutputPath(response.data.file_path);
      // setSummary(response.data.summary);
      setGeneratedPrompt(response.data.prompt);
      setSimilarity(response.data.clip_irss);
    } catch (err) {
      alert("Generation failed. See console.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-4 text-center">Composite Image Generator</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {images.map((img, index) => (
          <div key={index} className="border p-2 rounded text-center">
            <label className="block font-medium mb-1">{img.label}</label>

            {/* URL Input */}
            <input
              type="text"
              placeholder="Paste image URL or leave empty to upload"
              value={img.value.startsWith("http") ? img.value : ""}
              onChange={(e) => handleInputChange(index, e)}
              className="w-full border rounded p-1 text-sm mb-2"
            />

            {/* File Upload */}
            <div className="relative">
              {/* Hidden real file input */}
              <input
                type="file"
                accept="image/*"
                id={`file-input-${index}`}
                className="hidden"
                onChange={(e) => handleFileUpload(index, e)}
              />

              {/* Styled label acts as the upload button */}
              <label
                htmlFor={`file-input-${index}`}
                className="block bg-blue-600 text-white px-3 py-2 rounded cursor-pointer hover:bg-blue-700 text-sm"
              >
                Upload Image
              </label>
            </div>

            {/* Image Preview */}
            {img.value &&
              (img.value.startsWith("http") ||
                img.value.startsWith("data:image")) && (
                <>
                  <img
                    src={img.value}
                    alt={`Preview ${index + 1}`}
                    className="mt-2 w-full h-40 object-cover rounded border"
                  />
                  <p className="text-sm text-gray-600 italic">
                    Preview {index + 1}
                  </p>
                </>
              )}
          </div>
        ))}
      </div>

      <textarea
        placeholder="Enter your prompt..."
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        rows={4}
        className="w-full mt-4 p-2 border rounded"
      ></textarea>

      <button
        onClick={handleGenerate}
        disabled={loading}
        className="mt-4 bg-blue-600 text-white py-2 px-4 rounded"
      >
        {loading ? "Generating..." : "Submit"}
      </button>

      {outputPath && (
        <div className="mt-6">
          <h2 className="text-lg font-semibold mb-2">Output Image</h2>
          <img
            src={`http://localhost:8000/static/${outputPath.split("/").pop()}`}
            alt="Composite"
            className="rounded border max-w-full"
          />
        </div>
      )}
      <div className="mt-6 text-left">

        <h3 className="text-lg font-semibold mt-4 mb-2">
          Final Generated Prompt:
        </h3>
        <p className="text-gray-700 whitespace-pre-line">
          {generatedPrompt !== "" ? generatedPrompt : "Waiting for submission."}
        </p>

        <h3 className="text-lg font-semibold mt-4 mb-2">
          IRSS Score: (Quantitative metric showing how similar images are to
          prompt)
        </h3>
        <p className="text-gray-800 font-bold">
          {similarity !== null
            ? similarity.toFixed(4)
            : (
              <p className="text-gray-500 font-semibold">Image not generated yet.</p>
            )}
        </p>
      </div>
    </div>
  );
}
