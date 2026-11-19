use std::range::Range;
use unicode_segmentation::UnicodeSegmentation;
use unicode_width::UnicodeWidthStr;

#[derive(Debug, Clone, Copy)]
enum GraphemeWidth {
    Half,
    Full,
}

impl GraphemeWidth {
    const fn saturation_add(self, other: usize) -> usize {
        match self {
            Self::Half => other.saturating_add(1),
            Self::Full => other.saturating_add(2),
        }
    }
}

#[derive(Debug, Clone)]
struct TextFragment {
    grapheme: String,
    byte: usize,
    rendered_width: GraphemeWidth,
    replacement: Option<char>,
}

#[derive(Debug, Clone)]
pub struct LineLayout {
    fragments: Vec<TextFragment>,
}

impl LineLayout {
    pub const fn len(&self) -> usize {
        self.fragments.len()
    }

    pub fn get(&self, range: Range<usize>) -> String {
        self.visible(range)
            .into_iter()
            .map(|(_, text)| text)
            .collect()
    }

    /// Visible fragments retain their source grapheme indexes after cell clipping.
    pub fn visible(&self, range: Range<usize>) -> Vec<(usize, String)> {
        let mut result = Vec::new();
        if range.start >= range.end {
            return result;
        }
        let mut cell = 0;
        for (index, fragment) in self.fragments.iter().enumerate() {
            let end = fragment.rendered_width.saturation_add(cell);
            if cell >= range.end {
                break;
            }
            if end > range.start {
                let text = if end > range.end || cell < range.start {
                    "⋯".to_owned()
                } else if let Some(replacement) = fragment.replacement {
                    replacement.to_string()
                } else {
                    fragment.grapheme.clone()
                };
                result.push((index, text));
            }
            cell = end;
        }
        result
    }

    pub fn prefix_whitespace_count(&self) -> usize {
        self.fragments
            .iter()
            .take_while(|c| c.grapheme.chars().all(char::is_whitespace))
            .count()
    }

    pub fn width_until(&self, grapheme_index: usize) -> usize {
        self.fragments
            .iter()
            .take(grapheme_index)
            .map(|fragment| match fragment.rendered_width {
                GraphemeWidth::Half => 1,
                GraphemeWidth::Full => 2,
            })
            .sum()
    }

    pub fn byte_range(&self, grapheme: usize) -> Option<std::ops::Range<usize>> {
        let fragment = self.fragments.get(grapheme)?;
        Some(fragment.byte..fragment.byte.saturating_add(fragment.grapheme.len()))
    }

    pub fn width(&self) -> usize {
        self.width_until(self.len())
    }

    fn replacement_character(for_str: &str) -> Option<char> {
        let width = for_str.width();
        match for_str {
            " " => None,
            "\t" => Some(' '),
            _ if for_str.chars().any(char::is_control) => Some('▯'),
            _ if width > 0 && for_str.trim().is_empty() => Some('␣'),
            _ if width == 0 => {
                let mut chars = for_str.chars();
                if let Some(ch) = chars.next()
                    && ch.is_control()
                    && chars.next().is_none()
                {
                    return Some('▯');
                }
                Some('·')
            }
            _ => None,
        }
    }

    pub fn new(text: &str) -> Self {
        let fragments = text
            .grapheme_indices(true)
            .map(|(byte, grapheme)| {
                let (replacement, rendered_width) = Self::replacement_character(grapheme)
                    .map_or_else(
                        || {
                            let unicode_width = grapheme.width();
                            let rendered_width = match unicode_width {
                                0 | 1 => GraphemeWidth::Half,
                                _ => GraphemeWidth::Full,
                            };
                            (None, rendered_width)
                        },
                        |replacement| (Some(replacement), GraphemeWidth::Half),
                    );

                TextFragment {
                    grapheme: grapheme.to_string(),
                    byte,
                    rendered_width,
                    replacement,
                }
            })
            .collect();
        Self { fragments }
    }
}
