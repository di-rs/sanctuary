//! Attribute wrappers for `cli-testing`.

use proc_macro::TokenStream;
use quote::quote;
use syn::{FnArg, ItemFn, LitStr, Pat, ReturnType, Type, parse_macro_input};

/// Inject a named Rust-owned case and perform its standard checks automatically.
#[proc_macro_attribute]
pub fn test_case(attribute: TokenStream, item: TokenStream) -> TokenStream {
    let name = parse_macro_input!(attribute as LitStr);
    let function = parse_macro_input!(item as ItemFn);
    expand(&name, &function)
        .unwrap_or_else(syn::Error::into_compile_error)
        .into()
}

fn expand(name: &LitStr, function: &ItemFn) -> syn::Result<proc_macro2::TokenStream> {
    validate_function(function, "test_case")?;
    let signature = &function.sig;
    let Some(FnArg::Typed(argument)) = signature.inputs.first() else {
        return Err(syn::Error::new_spanned(
            signature,
            "#[test_case] requires exactly one parameter: cx: &mut Context",
        ));
    };
    if signature.inputs.len() != 1 {
        return Err(syn::Error::new_spanned(
            &signature.inputs,
            "#[test_case] requires exactly one parameter: cx: &mut Context",
        ));
    }
    let Type::Reference(reference) = argument.ty.as_ref() else {
        return Err(syn::Error::new_spanned(
            &argument.ty,
            "context must be borrowed as &mut Context",
        ));
    };
    if reference.mutability.is_none()
        || !matches!(reference.elem.as_ref(), Type::Path(path) if path.path.segments.last().is_some_and(|segment| segment.ident == "Context"))
    {
        return Err(syn::Error::new_spanned(
            &argument.ty,
            "context must be borrowed as &mut Context",
        ));
    }
    if !matches!(argument.pat.as_ref(), Pat::Ident(_)) {
        return Err(syn::Error::new_spanned(
            &argument.pat,
            "context parameter must be an identifier",
        ));
    }
    let unit = match &signature.output {
        ReturnType::Default => true,
        ReturnType::Type(_, ty) if matches!(ty.as_ref(), Type::Tuple(tuple) if tuple.elems.is_empty()) => {
            true
        }
        ReturnType::Type(_, ty) if matches!(ty.as_ref(), Type::Path(path) if unit_result(path)) => {
            false
        }
        other @ ReturnType::Type(..) => {
            return Err(syn::Error::new_spanned(
                other,
                "#[test_case] supports () or cli_testing::Result<()>",
            ));
        }
    };
    let attributes = &function.attrs;
    let visibility = &function.vis;
    let identifier = &signature.ident;
    let parameter = &argument.pat;
    let context_type = &argument.ty;
    let body = &function.block;
    let call = if unit {
        quote! { (|#parameter: #context_type| #body)(__cli_context); ::core::result::Result::Ok(()) }
    } else {
        let output = &signature.output;
        quote! { (|#parameter: #context_type| #output #body)(__cli_context) }
    };
    Ok(quote! {
        #(#attributes)*
        #[test]
        #visibility fn #identifier() -> ::cli_testing::Result<()> {
            ::cli_testing::customize(&::cli_testing::context!(), #name, |__cli_context| { #call })
        }
    })
}

fn unit_result(path: &syn::TypePath) -> bool {
    path.path.segments.last().is_some_and(|segment| {
        segment.ident == "Result" && match &segment.arguments {
            syn::PathArguments::None => true,
            syn::PathArguments::AngleBracketed(arguments) => arguments.args.len() == 1
                && matches!(arguments.args.first(), Some(syn::GenericArgument::Type(Type::Tuple(tuple))) if tuple.elems.is_empty()),
            syn::PathArguments::Parenthesized(_) => false,
        }
    })
}

fn conflicting_attribute(meta: &syn::Meta) -> syn::Result<bool> {
    if meta.path().is_ident("test") || meta.path().is_ident("should_panic") {
        return Ok(true);
    }
    if let syn::Meta::List(list) = meta
        && list.path.is_ident("cfg_attr")
    {
        let nested = list.parse_args_with(
            syn::punctuated::Punctuated::<syn::Meta, syn::Token![,]>::parse_terminated,
        )?;
        for attribute in nested.iter().skip(1) {
            if conflicting_attribute(attribute)? {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

fn validate_function(function: &ItemFn, attribute_name: &str) -> syn::Result<()> {
    let signature = &function.sig;
    if signature.asyncness.is_some()
        || signature.constness.is_some()
        || !matches!(signature.safety, syn::Safety::Default)
        || signature.abi.is_some()
        || !signature.generics.params.is_empty()
        || signature.generics.where_clause.is_some()
        || signature.variadic.is_some()
    {
        return Err(syn::Error::new_spanned(
            signature,
            format!("#[{attribute_name}] requires a synchronous, safe, nongeneric Rust function"),
        ));
    }
    for attribute in &function.attrs {
        if conflicting_attribute(&attribute.meta)? {
            return Err(syn::Error::new_spanned(
                attribute,
                format!(
                    "#[{attribute_name}] supplies #[test] and cannot be combined with #[test] or #[should_panic]"
                ),
            ));
        }
    }
    Ok(())
}

/// Inject package helpers into a native test without loading or executing a case.
#[proc_macro_attribute]
pub fn cli_test(attribute: TokenStream, item: TokenStream) -> TokenStream {
    let function = parse_macro_input!(item as ItemFn);
    let result = if attribute.is_empty() {
        expand_cli_test(&function)
    } else {
        Err(syn::Error::new_spanned(
            proc_macro2::TokenStream::from(attribute),
            "#[cli_test] takes no arguments; use #[test_case(\"name\")] for a catalog case",
        ))
    };
    result.unwrap_or_else(syn::Error::into_compile_error).into()
}

fn expand_cli_test(function: &ItemFn) -> syn::Result<proc_macro2::TokenStream> {
    validate_function(function, "cli_test")?;
    let signature = &function.sig;
    let argument = match signature.inputs.first() {
        Some(FnArg::Typed(argument)) if signature.inputs.len() == 1 => argument,
        _ => {
            return Err(syn::Error::new_spanned(
                signature,
                "#[cli_test] requires exactly one parameter: cx: &TestContext",
            ));
        }
    };
    if !matches!(argument.ty.as_ref(), Type::Reference(reference)
        if reference.mutability.is_none()
        && matches!(reference.elem.as_ref(), Type::Path(path)
            if path.path.segments.last().is_some_and(|segment| segment.ident == "TestContext")))
    {
        return Err(syn::Error::new_spanned(
            &argument.ty,
            "context must be borrowed as &TestContext",
        ));
    }
    if !matches!(argument.pat.as_ref(), Pat::Ident(_)) {
        return Err(syn::Error::new_spanned(
            &argument.pat,
            "context parameter must be an identifier",
        ));
    }
    let attributes = &function.attrs;
    let visibility = &function.vis;
    let identifier = &signature.ident;
    let output = &signature.output;
    let parameter = &argument.pat;
    let context_type = &argument.ty;
    let body = &function.block;
    Ok(quote! {
        #(#attributes)*
        #[test]
        #visibility fn #identifier() #output {
            let #parameter: #context_type = &::cli_testing::context!();
            #body
        }
    })
}
