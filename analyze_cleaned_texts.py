import os
import re
import matplotlib.pyplot as plt
from pathlib import Path

def count_sentences_after_separator(file_path):
    """
    Count sentences in a markdown file after the '========================================' separator.
    
    Args:
        file_path: Path to the markdown file
        
    Returns:
        Number of sentences found after the separator
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by the separator
        parts = content.split('========================================')
        
        # If there's no separator or nothing after it, return 0
        if len(parts) < 2:
            return 0
        
        # Get text after the separator
        text_after_separator = parts[1].strip()
        
        if not text_after_separator:
            return 0
        
        # Count sentences - split by sentence-ending punctuation followed by space or newline
        # This regex looks for . ! ? followed by whitespace or end of string
        sentences = re.split(r'[.!?]+(?:\s+|$)', text_after_separator)
        
        # Filter out empty strings and whitespace-only strings
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return len(sentences)
    
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return 0

def main():
    # Define the folder path
    folder_path = Path("cleaned")
    
    # Check if folder exists
    if not folder_path.exists():
        print(f"Error: Folder '{folder_path}' not found!")
        return
    
    # Get all markdown files
    md_files = list(folder_path.glob("*.md"))
    
    if not md_files:
        print(f"No markdown files found in '{folder_path}'")
        return
    
    print(f"Found {len(md_files)} markdown files")
    
    # Count sentences for each file
    sentence_counts = []
    for md_file in md_files:
        count = count_sentences_after_separator(md_file)
        sentence_counts.append(count)
        print(f"{md_file.name}: {count} sentences")
    
    # Create histogram
    plt.figure(figsize=(10, 6))
    plt.hist(sentence_counts, bins=20, edgecolor='black', alpha=0.7)
    plt.xlabel('Num Sentences', fontsize=12)
    plt.ylabel('Num Files', fontsize=12)
    plt.title('Sentence Counts in Markdown Files', fontsize=14)
    plt.grid(axis='y', alpha=0.3)
    
    # Add statistics to the plot
    avg_sentences = sum(sentence_counts) / len(sentence_counts) if sentence_counts else 0
    plt.axvline(avg_sentences, color='red', linestyle='--', linewidth=2, label=f'Mean: {avg_sentences:.1f}')
    plt.legend()
    
    # Save and show the plot
    output_file = 'sentence_count_histogram.png'
    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"\nHistogram saved as '{output_file}'")
    plt.show()
    
    # Print summary statistics
    print(f"\n--- Summary Statistics ---")
    print(f"Total files: {len(sentence_counts)}")
    print(f"Total sentences: {sum(sentence_counts)}")
    print(f"Average sentences per file: {avg_sentences:.2f}")
    print(f"Min sentences: {min(sentence_counts) if sentence_counts else 0}")
    print(f"Max sentences: {max(sentence_counts) if sentence_counts else 0}")

if __name__ == "__main__":
    main()